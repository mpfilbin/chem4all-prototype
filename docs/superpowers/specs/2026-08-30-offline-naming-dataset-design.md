# Design: Offline Local Naming Dataset (Replaces Live PubChem/CIR Lookup)

## Context

`docs/superpowers/specs/2026-07-24-iupac-name-multisource-design.md` (shipped in PR #16 / `v0.3.0`) built a PubChem-primary, CIR-fallback live HTTP naming path. In production use, PubChem's PUG REST service has proven too unreliable to depend on (recurring `503 PUGREST.ServerBusy` outages, not just the one-off spike documented in that design), and CIR — always a lesser fallback, with its own known slash-encoding gap for stereochemistry SMILES — does not return consistent enough results to compensate.

This design **fully retires** the live-API naming architecture from PR #16 and replaces it with an offline, locally-stored PubChem dataset: a pre-built index the app downloads once (and can refresh on demand), then queries with zero network dependency. There is no live-API fallback in the new design — a miss against the local dataset is a "not found," full stop.

Two supporting findings from spiking, both done empirically against real PubChem bulk data before committing to this approach:

- **InChIKey is a safe, toolkit-independent join key.** PubChem's bulk SMILES are Kekulé-form canonical, which does not match RDKit's own canonical SMILES form — naive string matching between "a SMILES DECIMER/RDKit produces" and "a SMILES in PubChem's bulk files" is not viable. InChIKey sidesteps this: it's a standardized, toolkit-independent hash. Validated by computing RDKit InChIKeys from PubChem's own bulk SMILES and comparing to PubChem's own published InChIKeys — **5000/5000 sampled compounds matched, 0 mismatches, 0 RDKit parse failures.**
- **Dataset size makes a full-universe bundle impractical, but download-not-bundle is viable.** Sampling real row lengths from PubChem's bulk files (avg IUPAC name 78.8 bytes, avg first-synonym 23.6 bytes, InChIKey 27 bytes) against the full ~119M-compound universe projects to **~15.4 GB raw / ~3.85 GB gzip-compressed** for just an `InChIKey → iupac_name, trivial_name` index. This ruled out bundling the full universe into the app installer. Filtering to compounds that have at least one synonym (i.e., anything with a common/trivial name — a reasonable proxy for "the kind of compound a chemistry course handout would show," per this app's actual use case) is expected to be meaningfully smaller, though this hasn't been measured directly against real data yet (see Section 2 caveat). Decoupling "download" from "bundle" already has precedent in this codebase: DECIMER's model weights are not shipped in the installer/DMG either — they're downloaded post-install via a Settings/main-screen action (`gui/model_manager.py`). This design reuses that exact pattern.

---

## Section 1 — Architecture & Data Flow

Two independent halves:

**Build side** (run manually/offline by a maintainer, not part of the shipped app): a new script, `pipeline/build_dataset.py`, downloads PubChem's bulk data files, filters/joins them into a single SQLite index keyed by InChIKey, gzips it, and the result is uploaded to Azure Blob Storage for the app to fetch.

**App side** (shipped in every install): `pipeline/namer.py` is rewritten to compute an RDKit InChIKey from the recognized SMILES and query a local SQLite file for `iupac_name` / `trivial_name`. If that local file isn't present yet, the lookup functions raise (see Section 6) rather than silently returning nothing — the user is expected to download it once via Settings (Section 5), the same way they'd first download the DECIMER model.

All live HTTP naming code (`_request_with_backoff`, `_pubchem_property`, `_pubchem_synonyms`, `_cir_iupac_name`, the `_MAX_RETRIES`/`_BACKOFF_BASE_SECONDS`/`_RETRYABLE_STATUS` retry machinery) is deleted outright, along with the runtime query cache it depended on (`pipeline/name_cache.py`'s `get_cached`/`set_cached` — there is nothing left to cache once lookups are local SQLite reads instead of network round-trips).

There is intentionally **no live-API fallback path** in the new design. A dataset miss (or dataset-not-downloaded) is reported as "not found" / a clear actionable state — not silently retried against the internet.

---

## Section 2 — Build Script (`pipeline/build_dataset.py`, new)

Not run by the app; run manually (or in CI) by a maintainer to produce the file that gets uploaded to Azure Storage. Five steps:

1. **Download** three PubChem bulk files from `https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/`:
   - `CID-InChI-Key.gz` (3 tab-separated columns: CID, InChI, InChIKey)
   - `CID-IUPAC.gz` (2 columns: CID, IUPAC name)
   - `CID-Synonym-filtered.gz` (2 columns: CID, synonym — multiple rows per CID, PubChem's own relevance-ordered synonym list)

   All three are CID-sorted, which is what makes step 3 a linear merge rather than requiring a full in-memory hash join.

2. **Filter** to the subset of CIDs present in `CID-Synonym-filtered.gz` — i.e., compounds that have at least one known synonym/trivial name. This is the "textbook-level compound" proxy that keeps the dataset well under the full-universe size, matching this app's actual use case (chemistry course handouts/presentations, not exhaustive research-database coverage).

3. **Join** the three streams by CID via a linear merge (single pass, since all inputs are CID-sorted) to produce rows of `(InChIKey, iupac_name, trivial_name)`, where `trivial_name` is the first synonym for that CID (matching `lookup_trivial_name`'s existing "first synonym" semantics from the old live-API design).

4. **Index**: write the joined rows into a single SQLite database file:

   ```sql
   CREATE TABLE names (
       inchikey     TEXT PRIMARY KEY,
       iupac_name   TEXT,
       trivial_name TEXT
   );
   ```

5. **Package**: gzip the resulting `.sqlite` file to `naming_dataset.sqlite.gz`, ready for upload to Azure Blob Storage (Section 8).

**Open caveat, not yet resolved:** only the *full-universe* size (~15.4 GB raw / ~3.85 GB compressed) has been empirically measured. The synonym-filtered subset's actual size hasn't been measured against real data — it's expected to be meaningfully smaller (reasonable, since most of PubChem's 119M compounds are synonym-less computational/PubChem-only entries), but this should be measured once the build script runs against real bulk files, before publishing the first dataset version. If it turns out not to be meaningfully smaller, the filter criteria may need revisiting.

Not covered by the pytest suite — this is a manually/CI-run maintainer tool operating on multi-GB external downloads, tested by inspection rather than unit tests (see Section 7).

---

## Section 3 — App-Side Lookup (`pipeline/name_dataset.py` new, `pipeline/namer.py` rewritten)

`pipeline/name_dataset.py` — owns the local SQLite file's path and readiness, plus the query itself (mirrors how `pipeline/name_cache.py` owned its own DB path in the old design, rather than the app pulling that from `gui/`):

```python
def dataset_path() -> Path:
    return Path(pystow.join("chem4all", "naming")) / "names.sqlite"

def is_dataset_ready() -> bool:
    return dataset_path().exists()

def lookup(inchikey: str) -> tuple[str | None, str | None]:
    """Returns (iupac_name, trivial_name), either or both None if not found.
    Raises if the dataset file is missing or unreadable."""
```

`pipeline/namer.py` — rewritten around RDKit + the local dataset, replacing all HTTP/retry code:

```python
from __future__ import annotations
from rdkit import Chem
from pipeline import name_dataset
from pipeline.salts import strip_to_parent


class NameLookupError(RuntimeError):
    """Unparseable SMILES, or the local dataset isn't downloaded yet."""


def _inchikey_for(smiles: str) -> str:
    canonical = strip_to_parent(smiles)
    mol = Chem.MolFromSmiles(canonical)
    if mol is None:
        raise NameLookupError(f"Could not parse SMILES: {canonical}")
    return Chem.MolToInchiKey(mol)


def lookup_iupac(smiles: str) -> str | None:
    if not name_dataset.is_dataset_ready():
        raise NameLookupError("Naming dataset not downloaded — see Settings.")
    iupac_name, _ = name_dataset.lookup(_inchikey_for(smiles))
    return iupac_name


def lookup_trivial_name(smiles: str) -> str | None:
    if not name_dataset.is_dataset_ready():
        raise NameLookupError("Naming dataset not downloaded — see Settings.")
    _, trivial_name = name_dataset.lookup(_inchikey_for(smiles))
    return trivial_name
```

This keeps `pipeline/` free of any `gui/` import, matching the codebase's existing one-way dependency direction (confirmed: `gui/worker.py` imports `pipeline.recognizer`, never the reverse).

`lookup_iupac`'s return type simplifies from `tuple[str | None, str]` (name + source) to plain `str | None`, since there's only one source now (Section 4).

---

## Section 4 — Data Model (`models/image_record.py`)

`iupac_source: str | None = None` (added in PR #16 to distinguish `'pubchem'` vs `'cir'`) is **removed outright**, not repurposed to a constant — with a single local dataset, there's no second source to distinguish.

- Remove from `to_review_dict()` / `from_review_dict()`.
- `gui/worker.py`: `record.iupac_name, record.iupac_source = lookup_iupac(smiles)` becomes `record.iupac_name = lookup_iupac(smiles)`.

---

## Section 5 — Settings UI & Dataset Download UX

### 5a. Remove the live-availability diagnostic UI

Delete from `gui/settings_dialog.py`: `_check_pubchem_available()`, `_check_cir_available()`, `_NamingAvailabilityCheckWorker`, `_build_naming_availability_section()` (and its call site), `_refresh_naming_availability()`, `_on_naming_availability_checked()`, and the worker-cleanup block in `done()`. There's nothing to "check" anymore — dataset presence is a synchronous file check, not a network probe.

### 5b. New module: `gui/dataset_manager.py`

Mirrors `gui/model_manager.py`'s `ModelDownloadWorker` pattern. Path/readiness (`dataset_path`, `is_dataset_ready`) come from `pipeline.name_dataset` (Section 3) — `gui/dataset_manager.py` only owns the download mechanics and the sidecar timestamp, which is purely a display concern:

```python
from pipeline.name_dataset import dataset_path, is_dataset_ready  # re-used, not redefined

DATASET_URL = "https://<account>.blob.core.windows.net/chem4all/naming_dataset.sqlite.gz"

def dataset_last_downloaded() -> datetime | None:
    """Reads a sidecar metadata file (names.sqlite.meta) written by the download step."""


class DatasetDownloadWorker(QThread):
    status = pyqtSignal(str)
    progress = pyqtSignal(int, int)   # bytes_done, total_bytes (download phase)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self) -> None:
        # stream DATASET_URL to a temp .gz file (chunked, same pattern as ModelDownloadWorker._download)
        # gunzip to a temp .sqlite, atomically replace dataset_path()
        # write sidecar: UTC download timestamp + source URL
```

The dataset lives under its own `pystow.join("chem4all", "naming")` home, deliberately separate from DECIMER's `pystow.join("DECIMER-V2")` home — different asset, different refresh cadence.

### 5c. Settings dialog: new "Naming Dataset" section

Replaces the deleted availability section in the same layout slot, modeled on the existing `_build_model_info()`:

```
┌─ Naming Dataset ──────────────────────────────────────┐
│ Status:  ✓ Downloaded  (last updated: 2026-08-12)      │
│ Location: /Users/.../chem4all/naming            [Show] │
│                                    [Refresh Dataset]    │
│ IUPAC and trivial names are looked up from a local      │
│ offline dataset. No internet connection is required.    │
└──────────────────────────────────────────────────────┘
```

- Status line: `✓ Downloaded (last updated: YYYY-MM-DD)` (green) or `✗ Not downloaded` (red), from `is_dataset_ready()` / `dataset_last_downloaded()`.
- Button label reads "Download Dataset" when absent, "Refresh Dataset" when present; always re-downloads from `DATASET_URL` on click regardless of current state.
- Two-phase progress (determinate during download, indeterminate during decompress via `progress.emit(0, 0)`) mirrors `ModelDownloadWorker` exactly. Button disabled during the run; status text and button label update on `finished`; `QMessageBox.warning` on `error`.
- Worker kept alive on `self._dataset_download_worker`; cleaned up in `done()` the same way the old naming-availability worker was.

### 5d. First-run "dataset missing" banner

Mirrors `gui/file_picker.py`'s DECIMER model banner (`_build_model_banner()`): a parallel `_build_dataset_banner()`, shown when `is_dataset_ready()` is false, with its own "Download Naming Dataset" button wired to the same `DatasetDownloadWorker`, hidden once the download finishes. A fresh install may show both the DECIMER-missing and dataset-missing banners simultaneously — acceptable, since they're independent, unrelated downloads.

---

## Section 6 — Error Handling Semantics

Three distinct outcomes for a lookup, none of which existed as a clean split under the old retry-based design:

1. **Unparseable SMILES** (`Chem.MolFromSmiles` returns `None`) — a DECIMER data-quality bug, not a naming-coverage gap. → raises `NameLookupError`.
2. **Dataset not downloaded yet** (`is_dataset_ready()` false) — an actionable state (user needs Settings → Download Dataset), not a per-compound miss. → raises `NameLookupError` with a message pointing at Settings.
3. **Confirmed miss** (SMILES parses, dataset present, InChIKey just isn't in the index) — a legitimate "not found." → returns `None`, no exception.

This keeps `gui/worker.py`'s existing `try/except NameLookupError` call-site shape intact from PR #16 — only the reasons a `NameLookupError` is raised change.

---

## Section 7 — Testing Strategy

- **`tests/test_name_dataset.py`** (new): `dataset_path()` / `is_dataset_ready()` against a `tmp_path`-based fake pystow home, plus `lookup()` against a small fixture SQLite DB (not the real multi-GB dataset) — exact hit, miss (`None`), missing dataset file, corrupt/malformed DB file (raises, doesn't silently return `None`).
- **`tests/test_namer.py`** (rewritten): mocks `pipeline.name_dataset.lookup`/`is_dataset_ready` instead of `requests` — no network mocking needed anywhere in this suite anymore. Cases per Section 6: hit, confirmed miss, unparseable SMILES, dataset-not-ready. Keeps the existing `strip_to_parent` interaction test (unchanged). Deletes the retry/backoff tests (`_request_with_backoff`, `_RetriesExhausted`) as dead code.
- **`tests/test_dataset_manager.py`** (new): `dataset_last_downloaded()` sidecar parsing against a `tmp_path`-based fake dataset file. `DatasetDownloadWorker` tested at whatever level `ModelDownloadWorker` currently is (match existing precedent rather than introducing asymmetric coverage).
- **`tests/test_worker.py`**: remove `test_worker_sets_iupac_source_from_lookup` (Section 4 fallout); update the `lookup_iupac`/`lookup_trivial_name` mock call shapes to the new plain-`str | None` signatures.
- **`tests/test_image_record.py`**: remove the three `iupac_source` tests (default, `to_review_dict`, `from_review_dict`).
- **Out of scope**: `pipeline/build_dataset.py` (manually/CI-run maintainer tool against real multi-GB bulk files — tested by inspection, not pytest) and the real Azure Storage URL (always mocked).

```bash
python -m pytest tests/ -v
```

---

## Section 8 — Dependencies & Azure Storage Mechanics

### `pyproject.toml`

Add `rdkit` (pinned to `2026.03.4`, the version validated during spiking) alongside existing dependencies. Full PyPI wheel coverage for all four target platforms (macOS ARM64/Intel, Windows, Linux) — same packaging tier as the existing DECIMER/TensorFlow dependency, no new packaging risk.

### Azure Blob Storage

- **Container**: `chem4all`, public **anonymous read access** enabled at the container level (not the whole storage account) — standard pattern for unauthenticated static-file download, letting `DatasetDownloadWorker` do a plain `requests.get(url, stream=True)` with no credentials, matching `ModelDownloadWorker`'s zero-auth Zenodo download.
- **Blob name**: `naming_dataset.sqlite.gz` at the container root — no versioned path, since only a *local* download timestamp is tracked (Section 5), not a dataset version. "Refresh Dataset" just re-fetches whatever currently sits at that URL.
- **URL**: `https://<account>.blob.core.windows.net/chem4all/naming_dataset.sqlite.gz`, hardcoded as `DATASET_URL` in `gui/dataset_manager.py` — same hardcoding style as `MODEL_URLS` in `gui/model_manager.py`.
- **Publishing** is a manual step (run `pipeline/build_dataset.py`, then `az storage blob upload` or the Portal) — not automated as part of this design, matching the build script's own manually-run nature.
- **Open item**: the storage *account* name itself (`<account>` above) isn't chosen yet — left as a placeholder until provisioned.
