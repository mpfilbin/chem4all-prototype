# Design: Multi-Source IUPAC & Trivial Name Lookup (PubChem / CIR)

> **Superseded.** The live PubChem/CIR lookup path described here has been fully retired in favour of the offline local naming dataset — see [`2026-08-30-offline-naming-dataset-design.md`](2026-08-30-offline-naming-dataset-design.md). Kept for historical context only.

## Context

`docs/smiles-to-iupac.md` proposed replacing the current OpenRouter/GPT-4o naming path (`pipeline/namer.py`) with a single direct integration against PubChem's PUG REST API. Before committing to that design, we spiked the live PubChem service and found it in a genuine `503 PUGREST.ServerBusy` outage — reproducible across every endpoint tested (property lookup, synonyms, description, even the lightest possible fixed-CID fetch), while `pubchem.ncbi.nlm.nih.gov`'s main website loaded fine. This demonstrated, live, the exact risk the original spec's §10 accepted but didn't design around.

This design supersedes §6–§9 of `docs/smiles-to-iupac.md` with a two-source approach: PubChem primary, NCI/CADD Chemical Identifier Resolver (CIR) as an automatic fallback for IUPAC names. It also folds trivial/common name lookup (currently `lookup_trivial_name`, also OpenRouter-based, previously out of scope in the original doc) into the same replacement.

Key findings from spiking:
- **CIR** (`cactus.nci.nih.gov`) is a separate NIH-hosted service, live during the PubChem outage. It correctly resolved IUPAC names for simple structures (`aspirin → 2-acetyloxybenzoic acid`) but has a structural flaw: its GET/path-based API returns 404 for any SMILES containing `/` (e.g. E/Z stereochemistry) because its server rejects percent-encoded `%2F` in URL paths. Its `names` endpoint mixes CAS numbers and systematic names with no reliable common-name signal, so it's unsuitable for trivial names.
- **STOUT v2 was investigated and rejected for v1.** It looked promising at first — a real published PyPI package (`STOUT-pypi`, MIT, from the same lab that publishes DECIMER), with weights recoverable via Zenodo despite the original host 404ing, and 83–89% exact-match accuracy per its own paper. But a live install attempt found a hard, unresolvable dependency conflict: `STOUT-pypi` pins `tensorflow==2.10.1` exactly, while DECIMER (already in this app) requires `tensorflow>=2.12.0,<=2.20.0` — non-overlapping ranges that `pip` cannot satisfy in one environment. Supporting STOUT would require isolating it in a second Python environment/subprocess, packaged separately in the PyInstaller build, with its own IPC boundary — a large architectural addition on top of an already-marginal accuracy tradeoff. Not worth it for v1; revisit if STOUT resolves its TensorFlow pin, or if offline naming becomes a real, reported need (per `docs/smiles-to-iupac.md` §11's revisit triggers).

---

## Section 1 — Naming Backends & Lookup Flow (`pipeline/namer.py`, rewritten)

One IUPAC-name path: PubChem PUG REST primary; on error/timeout after retries, fall back to CIR. A "not found" from PubChem is cached and does *not* block trying CIR (they're independent signals, not conflated).

Trivial name lookup is **always** PubChem-only (`property/IUPACName` has no trivial-name equivalent; CIR's synonym list proved unreliable in spiking).

```python
from __future__ import annotations
import requests
from pipeline.name_cache import get_cached, set_cached
from pipeline.salts import strip_to_parent  # new helper, see Task 1 — no such helper exists today

_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CIR_BASE = "https://cactus.nci.nih.gov/chemical/structure"


class NameLookupError(RuntimeError):
    """All applicable sources failed after retries — distinct from a confirmed 'not found'."""


def lookup_iupac(smiles: str) -> tuple[str | None, str]:
    """Returns (name_or_None, source) where source is 'pubchem' | 'cir'.
    Raises NameLookupError only when every applicable source errors out."""
    canonical = strip_to_parent(smiles)
    cached = get_cached(canonical, "iupac", "pubchem")
    if cached is not None and cached[1]:
        return cached[0], "pubchem"

    pubchem_reachable = True
    if cached is None:
        try:
            name = _pubchem_property(canonical, "IUPACName")
        except _RetriesExhausted:
            pubchem_reachable = False
        else:
            set_cached(canonical, "iupac", "pubchem", name)
            if name is not None:
                return name, "pubchem"

    cached_cir = get_cached(canonical, "iupac", "cir")
    if cached_cir is not None:
        return (cached_cir[0], "cir") if cached_cir[1] else (None, "cir")

    try:
        name = _cir_iupac_name(canonical)  # None on CIR's 404 (not-found or slash-encoding gap)
    except _RetriesExhausted as exc:
        reason = "PubChem and CIR both unreachable" if not pubchem_reachable else "CIR unreachable"
        raise NameLookupError(f"IUPAC lookup failed for {canonical}: {reason}") from exc

    set_cached(canonical, "iupac", "cir", name)
    return name, "cir"


def lookup_trivial_name(smiles: str) -> str | None:
    canonical = strip_to_parent(smiles)
    cached = get_cached(canonical, "trivial", "pubchem")
    if cached is not None:
        return cached[0] if cached[1] else None
    try:
        synonyms = _pubchem_synonyms(canonical)  # list[str], [] if none
    except _RetriesExhausted as exc:
        raise NameLookupError(f"Trivial name lookup failed for {canonical}: PubChem unreachable") from exc
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
```

Retry/backoff policy for PubChem and CIR follows the original spec's §8.2 (exponential backoff, capped retries, honor `Retry-After` when present — confirmed present and correct in spiking). CIR gets its own conservative client-side throttle since it publishes no formal rate-limit policy.

---

## Section 2 — Caching (`pipeline/name_cache.py`, new)

```sql
CREATE TABLE name_cache (
    smiles      TEXT NOT NULL,
    name_type   TEXT NOT NULL,   -- 'iupac' | 'trivial'
    source      TEXT NOT NULL,   -- 'pubchem' | 'cir'
    name        TEXT,            -- NULL if queried and no match found
    found       INTEGER NOT NULL,
    queried_at  TEXT NOT NULL,
    PRIMARY KEY (smiles, name_type, source)
);
```

Deviates from `docs/smiles-to-iupac.md` §8.3's single-source `iupac_cache` table: with two possible sources, a name can't be cached by SMILES alone — a CIR result and a PubChem-confirmed result for the same SMILES are independent signals (e.g. CIR's slash-encoding gap can produce a false "not found" that shouldn't be conflated with a genuine PubChem miss).

```python
def get_cached(smiles: str, name_type: str, source: str) -> tuple[str | None, bool] | None:
    """Returns (name, found) or None if no cache row exists yet."""

def set_cached(smiles: str, name_type: str, source: str, name: str | None) -> None:
    """found = name is not None. Upserts on the (smiles, name_type, source) key."""
```

Stored at `~/.chem4all/name_cache.db`, alongside `config.json` and the DECIMER model cache.

---

## Section 3 — Config (`config.py`)

No new fields. (STOUT's `stout_enabled` toggle was dropped along with STOUT itself.)

---

## Section 4 — Settings Dialog (`gui/settings_dialog.py`)

- **Availability badges (diagnostic only, no toggle attached):** on dialog open, fire a lightweight check against PubChem (`IUPACName` for a fixed known SMILES, e.g. `CCO`) and CIR similarly; render `● Available` / `● Unavailable` / `○ Unknown` (network error during the check itself) per service. A "Recheck" button re-runs both on demand — no background polling while the dialog is open. Purpose: when a user sees slow/failed name lookups, this explains why (e.g. "PubChem: Unavailable" tells them the app is already falling back to CIR automatically) without requiring a decision from them.
- The existing OpenRouter API key field's label/tooltip narrows to reflect it now only backs the "Describe Image" feature (`pipeline/describer.py`), not naming.

---

## Section 5 — Data Model (`models/image_record.py`)

Add field:

```python
iupac_source: str | None = None  # 'pubchem' | 'cir'
```

- `to_review_dict()` / `from_review_dict()` gain `iupac_source`.
- Not surfaced in `result_lines()` display text — both sources are equally "database-confirmed," so there's no confidence distinction worth showing the user (unlike the dropped STOUT case). The field exists for cache correctness (Section 2) and potential future diagnostics/logging, not UI display.
- Trivial name has only one possible source (PubChem), so no `trivial_source` field is needed.

---

## Section 6 — Worker (`gui/worker.py`)

Replace the `lookup_iupac`/`lookup_trivial_name` calls (currently passing `api_key` and `record.recognition_bytes` for the OpenRouter multimodal path) with the new signatures:

```python
if "iupac" in types and smiles:
    try:
        record.iupac_name, record.iupac_source = lookup_iupac(smiles)
    except NameLookupError as exc:
        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

if "trivial" in types and smiles:
    try:
        record.trivial_name = lookup_trivial_name(smiles)
    except NameLookupError as exc:
        self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")
```

`record.recognition_bytes` is no longer passed to naming calls (the image was only ever used for the old multimodal OpenRouter path); it's still cleared as before for the `description` path.

---

## Testing

- `tests/test_namer.py` — rewritten around mocked `requests.post`/`requests.get` for PubChem and CIR separately (replacing OpenRouter mocks); cache hit/miss cases; PubChem-fails-CIR-succeeds and both-fail cases.
- `tests/test_name_cache.py` — new; upsert, per-source independence, `found=False` vs. no-row-yet distinction.
- `tests/test_worker.py` — mocks updated to the new `lookup_iupac`/`lookup_trivial_name` signatures; assert `iupac_source` is set correctly per case.
- `tests/test_image_record.py` — `iupac_source` default, serialization roundtrip.
- `tests/test_config.py` — no changes needed (no new config fields).

```bash
python -m pytest tests/ -v
```
