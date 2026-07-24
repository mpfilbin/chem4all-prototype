# Design: Multi-Source IUPAC & Trivial Name Lookup (PubChem / CIR / STOUT)

## Context

`docs/smiles-to-iupac.md` proposed replacing the current OpenRouter/GPT-4o naming path (`pipeline/namer.py`) with a single direct integration against PubChem's PUG REST API. Before committing to that design, we spiked the live PubChem service and found it in a genuine `503 PUGREST.ServerBusy` outage — reproducible across every endpoint tested (property lookup, synonyms, description, even the lightest possible fixed-CID fetch), while `pubchem.ncbi.nlm.nih.gov`'s main website loaded fine. This demonstrated, live, the exact risk the original spec's §10 accepted but didn't design around.

This design supersedes §6–§9 of `docs/smiles-to-iupac.md` with a three-source approach: PubChem primary, NCI/CADD Chemical Identifier Resolver (CIR) as an automatic fallback for IUPAC names, and an opt-in fully-offline STOUT v2 backend the user can switch to entirely. It also folds trivial/common name lookup (currently `lookup_trivial_name`, also OpenRouter-based, previously out of scope in the original doc) into the same replacement.

Key findings from spiking:
- **CIR** (`cactus.nci.nih.gov`) is a separate NIH-hosted service, live during the PubChem outage. It correctly resolved IUPAC names for simple structures (`aspirin → 2-acetyloxybenzoic acid`) but has a structural flaw: its GET/path-based API returns 404 for any SMILES containing `/` (e.g. E/Z stereochemistry) because its server rejects percent-encoded `%2F` in URL paths. Its `names` endpoint mixes CAS numbers and systematic names with no reliable common-name signal, so it's unsuitable for trivial names.
- **STOUT v2** (`STOUT-pypi`, MIT, from the same lab that publishes DECIMER) is a real published package, not the alpha/unlisted situation that ruled out the earlier `smiles2iupac` option. Its weights (blocked at the original hosting URL, 404 since ~May 2026) are mirrored on Zenodo. Its own paper reports 83–89% exact-match accuracy — good enough to be useful, not good enough to present as equivalent to a database-confirmed name.
- The app already bundles `torch`/`tensorflow` for DECIMER through a signed, notarized PyInstaller build, so the original spec's "avoid compiled dependencies" rejection of ML-based options no longer holds on packaging-risk grounds — only on accuracy-confidence grounds, which is a real but different concern addressed below by keeping STOUT opt-in and clearly labeled.

---

## Section 1 — Naming Backends & Lookup Flow (`pipeline/namer.py`, rewritten)

Two mutually exclusive IUPAC-name backends, selected by `config.stout_enabled` — never blended within a single lookup:

- **Default (network) backend:** PubChem PUG REST primary; on error/timeout after retries, fall back to CIR. A "not found" from PubChem is cached and does *not* block trying CIR (they're independent signals, not conflated).
- **Opt-in (local) backend:** STOUT v2 only, once the user has enabled it and its weights are present.

Trivial name lookup is **always** PubChem-only (`property/IUPACName` has no trivial-name equivalent; CIR's synonym list proved unreliable in spiking, and STOUT doesn't generate trivial names at all) — independent of the `stout_enabled` toggle.

```python
from __future__ import annotations
import requests
from pipeline.name_cache import get_cached, set_cached
from pipeline.salts import strip_to_parent  # existing helper per §8.4, salt/mixture stripping

_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CIR_BASE = "https://cactus.nci.nih.gov/chemical/structure"


class NameLookupError(RuntimeError):
    """All applicable sources failed after retries — distinct from a confirmed 'not found'."""


def lookup_iupac(smiles: str, stout_enabled: bool) -> tuple[str | None, str]:
    """Returns (name_or_None, source) where source is 'pubchem' | 'cir' | 'stout'.
    Raises NameLookupError only when every applicable source errors out."""
    canonical = strip_to_parent(smiles)
    if stout_enabled:
        return _lookup_stout(canonical)
    return _lookup_iupac_networked(canonical)


def _lookup_iupac_networked(smiles: str) -> tuple[str | None, str]:
    cached = get_cached(smiles, "iupac", "pubchem")
    if cached is None:
        try:
            name = _pubchem_property(smiles, "IUPACName")
            set_cached(smiles, "iupac", "pubchem", name)
            cached = (name, name is not None)
        except _RetriesExhausted:
            cached = None  # fall through to CIR without caching a failure
    if cached is not None and cached[1]:
        return cached[0], "pubchem"

    cached = get_cached(smiles, "iupac", "cir")
    if cached is not None:
        return (cached[0], "cir") if cached[1] else (None, "cir")
    try:
        name = _cir_iupac_name(smiles)  # None on CIR's 404 (not-found or slash-encoding gap)
        set_cached(smiles, "iupac", "cir", name)
        return name, "cir"
    except _RetriesExhausted as exc:
        raise NameLookupError(f"IUPAC lookup failed for {smiles}: PubChem and CIR both unreachable") from exc


def lookup_trivial_name(smiles: str) -> str | None:
    canonical = strip_to_parent(smiles)
    cached = get_cached(canonical, "trivial", "pubchem")
    if cached is not None:
        return cached[0] if cached[1] else None
    synonyms = _pubchem_synonyms(canonical)  # list[str], [] if none
    name = synonyms[0] if synonyms else None  # first synonym per PubChem's relevance ordering
    set_cached(canonical, "trivial", "pubchem", name)
    return name


def _pubchem_property(smiles: str, prop: str) -> str | None:
    """POST to /compound/smiles/property/{prop}/TXT — POST avoids URL-encoding
    conflicts with SMILES characters (/, \\, #). Raises _RetriesExhausted on
    429/5xx after backoff; returns None on PubChem's 404 'not found'."""
    ...


def _pubchem_synonyms(smiles: str) -> list[str]:
    """POST to /compound/smiles/synonyms/TXT, same retry/backoff policy."""
    ...


def _cir_iupac_name(smiles: str) -> str | None:
    """GET {_CIR_BASE}/{smiles}/iupac_name. Returns None on 404 (covers both
    genuine not-found and the known slash-encoding limitation — indistinguishable
    from CIR's response alone)."""
    ...


def _lookup_stout(smiles: str) -> tuple[str | None, str]:
    """Local inference via STOUT-pypi; no network, no rate limit, no cache miss
    path needed beyond the usual per-source cache row (source='stout')."""
    ...
```

Retry/backoff policy for PubChem and CIR follows the original spec's §8.2 (exponential backoff, capped retries, honor `Retry-After` when present — confirmed present and correct in spiking). CIR gets its own conservative client-side throttle since it publishes no formal rate-limit policy.

---

## Section 2 — Caching (`pipeline/name_cache.py`, new)

```sql
CREATE TABLE name_cache (
    smiles      TEXT NOT NULL,
    name_type   TEXT NOT NULL,   -- 'iupac' | 'trivial'
    source      TEXT NOT NULL,   -- 'pubchem' | 'cir' | 'stout'
    name        TEXT,            -- NULL if queried and no match found
    found       INTEGER NOT NULL,
    queried_at  TEXT NOT NULL,
    PRIMARY KEY (smiles, name_type, source)
);
```

Deviates from `docs/smiles-to-iupac.md` §8.3's single-source `iupac_cache` table: with three possible sources, a name can't be cached by SMILES alone — a STOUT estimate and a PubChem-confirmed name for the same SMILES are different values that must not overwrite or masquerade as each other when the user toggles backends.

```python
def get_cached(smiles: str, name_type: str, source: str) -> tuple[str | None, bool] | None:
    """Returns (name, found) or None if no cache row exists yet."""

def set_cached(smiles: str, name_type: str, source: str, name: str | None) -> None:
    """found = name is not None. Upserts on the (smiles, name_type, source) key."""
```

Stored at `~/.chem4all/name_cache.db`, alongside `config.json` and the DECIMER/STOUT model caches.

---

## Section 3 — STOUT Model Manager (`gui/model_manager.py`, extended)

Follows the existing DECIMER pattern in the same file — kept as parallel functions rather than merged into `MODEL_URLS`/`is_model_ready()`, since DECIMER's readiness must stay independent of whether STOUT is ever enabled.

**Weights URL is not yet resolved.** Zenodo record 6559438 (the one referenced by STOUT's own README as the "V2" release) is a 510 KB source-code snapshot, not the multi-GB model weights — the original weights host (`storage.googleapis.com/decimer_weights/...`) 404s. `STOUT-pypi`'s own download logic (triggered internally on first import) presumably points at wherever the maintainers moved the weights; the first implementation task for this section is installing `STOUT-pypi` in isolation, tracing its download call, and confirming a working weights URL — this app's downloader then points at that same confirmed URL rather than reimplementing STOUT's own fetch logic blind.

```python
STOUT_MODEL_URL = "..."  # set once confirmed per the note above

def _stout_home() -> Path | None: ...

def is_stout_model_ready() -> bool: ...

class StoutModelDownloadWorker(QThread):
    """Same shape as ModelDownloadWorker: status/progress/finished/error signals,
    streamed download + zip extraction, .model_url version marker for re-download
    on URL change."""

class StoutModelPreloadWorker(QThread):
    """Same shape as ModelPreloadWorker: runs one dummy inference to force
    weight loading before first real use, emits finished(elapsed_seconds)."""
```

---

## Section 4 — Config (`config.py`)

Add field:

```python
stout_enabled: bool = False
```

No separate "preload STOUT" flag — enabling STOUT implies wanting it warm, matching Section 5.

---

## Section 5 — App Startup (`gui/app.py`)

Extend the existing DECIMER preload block:

```python
if config.preload_model and is_model_ready():
    from gui.model_manager import ModelPreloadWorker
    ...  # existing

if config.stout_enabled and is_stout_model_ready():
    from gui.model_manager import StoutModelPreloadWorker
    ...  # same wiring pattern, independent QThread
```

Both preload workers can run concurrently — they're independent.

---

## Section 6 — Settings Dialog (`gui/settings_dialog.py`)

- **Availability badges:** on dialog open, fire a lightweight check against PubChem (`IUPACName` for a fixed known SMILES, e.g. `CCO`) and CIR similarly; render `● Available` / `● Unavailable` / `○ Unknown` (network error during the check itself) per service. A "Recheck" button re-runs both on demand — no background polling while the dialog is open.
- **STOUT toggle:** checkbox, always clickable. Checking it when weights aren't yet present triggers `StoutModelDownloadWorker` with a progress bar (mirrors the existing DECIMER download UI at the current `MODEL_URLS`/`_decimer_home` import site); `config.stout_enabled` is only set `True` on successful download completion (a failed/cancelled download leaves the checkbox unchecked). Once weights are present, toggling on/off is instant and doesn't re-download or delete them.
- Inline copy ties the two together, e.g.: "PubChem: ● Unavailable — consider enabling offline AI naming below."
- The existing OpenRouter API key field's label/tooltip narrows to reflect it now only backs the "Describe Image" feature (`pipeline/describer.py`), not naming.

---

## Section 7 — Data Model (`models/image_record.py`)

Add field:

```python
iupac_source: str | None = None  # 'pubchem' | 'cir' | 'stout'
```

- `to_review_dict()` / `from_review_dict()` gain `iupac_source`.
- `result_lines()` appends `" (AI estimate)"` to the IUPAC line when `iupac_source == "stout"`, so the low-confidence label survives into the review screen and any exported document — not just a transient UI badge.
- Trivial name has only one possible source (PubChem), so no `trivial_source` field is needed.

---

## Section 8 — Worker (`gui/worker.py`)

Replace the `lookup_iupac`/`lookup_trivial_name` calls (currently passing `api_key` and `record.recognition_bytes` for the OpenRouter multimodal path) with the new signatures:

```python
if "iupac" in types and smiles:
    try:
        record.iupac_name, record.iupac_source = lookup_iupac(smiles, self._config.stout_enabled)
    except NameLookupError as exc:
        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

if "trivial" in types and smiles:
    try:
        record.trivial_name = lookup_trivial_name(smiles)
    except NameLookupError as exc:
        self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")
```

`self._config.stout_enabled` is read fresh per record (not snapshotted at batch start), so a mid-batch settings change takes effect on subsequent records — safe because `iupac_source` is tagged per-record, so a batch with mixed sources is still correctly labeled rather than ambiguous. `record.recognition_bytes` is no longer passed to naming calls (the image was only ever used for the old multimodal OpenRouter path); it's still cleared as before for the `description` path.

---

## Testing

- `tests/test_namer.py` — rewritten around mocked `requests.post`/`requests.get` for PubChem and CIR separately (replacing OpenRouter mocks); cache hit/miss cases; PubChem-fails-CIR-succeeds and both-fail cases; STOUT path mocked at the inference boundary.
- `tests/test_name_cache.py` — new; upsert, per-source independence, `found=False` vs. no-row-yet distinction.
- `tests/test_model_manager.py` — extended with a parallel `StoutModelDownloadWorker`/`StoutModelPreloadWorker` test class following the existing DECIMER test pattern.
- `tests/test_worker.py` — mocks updated to the new `lookup_iupac`/`lookup_trivial_name` signatures; assert `iupac_source` is set correctly per case.
- `tests/test_image_record.py` — `iupac_source` default, serialization roundtrip, `result_lines()` STOUT-suffix behavior.
- `tests/test_config.py` — `stout_enabled` default and roundtrip.

```bash
python -m pytest tests/ -v
```
