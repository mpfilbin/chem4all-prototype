# Multi-Source IUPAC/Trivial Name Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the OpenRouter/GPT-4o naming path (`pipeline/namer.py`) with PubChem PUG REST (primary) + CIR (automatic IUPAC-only fallback), backed by a persistent SQLite cache.

**Architecture:** `pipeline/namer.py` exposes `lookup_iupac(smiles)` and `lookup_trivial_name(smiles)`. IUPAC lookups try PubChem first, falling back to CIR on error or "not found"; trivial name lookups always use PubChem only. Both read/write a shared SQLite cache keyed by `(smiles, name_type, source)`. `gui/worker.py` calls these from its existing per-record `QThread` loop. `gui/settings_dialog.py` gains PubChem/CIR availability badges as a diagnostic (no toggle attached — there is no second backend to switch to; see the design doc's Context section for why STOUT v2 was investigated and rejected: a hard, unresolvable `tensorflow` version conflict with DECIMER).

**Tech Stack:** Python 3.9–3.12, `requests` (already a dependency), stdlib `sqlite3`, PyQt6 `QThread`.

## Global Constraints

- GPL-compatible, free for academic/non-commercial use (per `docs/smiles-to-iupac.md` §5).
- No new compiled/native dependency — PubChem and CIR are both pure `requests`/HTTP.
- PubChem usage policy caps requests at ~5/s; CIR gets an equally conservative self-imposed client-side cap (it publishes no formal limit).
- All naming lookups run off the Qt main thread — `gui/worker.py`'s existing `RecognizerWorker(QThread)` loop; no new threading model needed.
- Salt/mixture SMILES are stripped to the largest `.`-separated fragment before every lookup, regardless of source.
- Cache keys must be `(smiles, name_type, source)` — never collapse different sources into one row (design doc §2: a CIR result and a PubChem-confirmed result for the same SMILES are independent signals, since CIR's slash-encoding gap can produce a false "not found").

---

### Task 1: Salt/mixture stripping (`pipeline/salts.py`)

**Files:**
- Create: `pipeline/salts.py`
- Test: `tests/test_salts.py`

**Interfaces:**
- Produces: `strip_to_parent(smiles: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
from pipeline.salts import strip_to_parent


def test_strip_to_parent_single_component_unchanged():
    assert strip_to_parent("CCO") == "CCO"


def test_strip_to_parent_picks_largest_fragment():
    # sodium acetate: acetate ion is the larger/parent fragment
    assert strip_to_parent("CC(=O)[O-].[Na+]") == "CC(=O)[O-]"


def test_strip_to_parent_three_fragments():
    assert strip_to_parent("[Cl-].[Cl-].CC(C)(C)N") == "CC(C)(C)N"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_salts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.salts'`

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations


def strip_to_parent(smiles: str) -> str:
    fragments = smiles.split(".")
    if len(fragments) == 1:
        return smiles
    return max(fragments, key=len)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_salts.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/salts.py tests/test_salts.py
git commit -m "feat: add salt/mixture stripping for name lookups"
```

---

### Task 2: Persistent name cache (`pipeline/name_cache.py`)

**Files:**
- Create: `pipeline/name_cache.py`
- Test: `tests/test_name_cache.py`

**Interfaces:**
- Produces: `get_cached(smiles: str, name_type: str, source: str, db_path: Path | None = None) -> tuple[str | None, bool] | None`
- Produces: `set_cached(smiles: str, name_type: str, source: str, name: str | None, db_path: Path | None = None) -> None`
- Produces: module constant `DEFAULT_DB_PATH: Path` (equals `Path.home() / ".chem4all" / "name_cache.db"`)

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
from pipeline.name_cache import get_cached, set_cached


def test_get_cached_returns_none_when_no_row(tmp_path):
    db = tmp_path / "cache.db"
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) is None


def test_set_then_get_cached_found(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)


def test_set_cached_none_records_not_found(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("XYZ123", "iupac", "pubchem", None, db_path=db)
    assert get_cached("XYZ123", "iupac", "pubchem", db_path=db) == (None, False)


def test_cache_is_independent_per_source(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "cir", db_path=db) is None


def test_cache_is_independent_per_name_type(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "trivial", "pubchem", db_path=db) is None


def test_set_cached_upserts_existing_row(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "wrong-name", db_path=db)
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)


def test_cache_persists_across_connections(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    # Simulate app restart: a fresh call re-opens the same file.
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_name_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.name_cache'`

- [ ] **Step 3: Write the implementation**

```python
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".chem4all" / "name_cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS name_cache (
    smiles      TEXT NOT NULL,
    name_type   TEXT NOT NULL,
    source      TEXT NOT NULL,
    name        TEXT,
    found       INTEGER NOT NULL,
    queried_at  TEXT NOT NULL,
    PRIMARY KEY (smiles, name_type, source)
);
"""


def _connect(db_path: Path | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    return conn


def get_cached(
    smiles: str, name_type: str, source: str, db_path: Path | None = None
) -> tuple[str | None, bool] | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT name, found FROM name_cache WHERE smiles = ? AND name_type = ? AND source = ?",
            (smiles, name_type, source),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    name, found = row
    return (name, bool(found))


def set_cached(
    smiles: str, name_type: str, source: str, name: str | None, db_path: Path | None = None
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO name_cache (smiles, name_type, source, name, found, queried_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(smiles, name_type, source) DO UPDATE SET
                name = excluded.name,
                found = excluded.found,
                queried_at = excluded.queried_at
            """,
            (smiles, name_type, source, name, int(name is not None), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_name_cache.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/name_cache.py tests/test_name_cache.py
git commit -m "feat: add persistent SQLite cache for multi-source name lookups"
```

---

### Task 3: `ImageRecord.iupac_source` field (`models/image_record.py`)

**Files:**
- Modify: `models/image_record.py`
- Test: `tests/test_image_record.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `ImageRecord.iupac_source: str | None = None` (values `"pubchem" | "cir" | None`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_image_record.py`:

```python
def test_image_record_iupac_source_default():
    record = ImageRecord(
        id="abc123", source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb", recognition_bytes=b"recog",
    )
    assert record.iupac_source is None


def test_to_review_dict_includes_iupac_source():
    record = ImageRecord(
        id="abc123", source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb", recognition_bytes=b"recog",
        iupac_name="ethanol", iupac_source="cir",
    )
    assert record.to_review_dict()["iupac_source"] == "cir"


def test_from_review_dict_restores_iupac_source():
    d = {
        "id": "abc123", "source_ref": "slide 1, shape 1",
        "iupac_name": "ethanol", "iupac_source": "pubchem",
        "prediction_types": ["iupac"],
    }
    record = ImageRecord.from_review_dict(d)
    assert record.iupac_source == "pubchem"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_image_record.py -v`
Expected: FAIL — `TypeError` on `iupac_source` kwarg and `AttributeError`/`KeyError` on the missing field.

- [ ] **Step 3: Implement**

In `models/image_record.py`, add the field after `trivial_name` (currently `models/image_record.py:17`):

```python
    trivial_name: str | None = None
    iupac_source: str | None = None  # 'pubchem' | 'cir'
```

Update `to_review_dict()` (`models/image_record.py:45-57`) — add `"iupac_source": self.iupac_source,` alongside `"iupac_name"`.

Update `from_review_dict()` (`models/image_record.py:59-78`) — add `iupac_source=d.get("iupac_source"),` alongside `iupac_name=d.get("iupac_name")`.

`result_lines()` is unchanged — both sources are equally "database-confirmed," so there's no UI distinction to render (unlike a since-dropped local-inference backend would have needed).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_image_record.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "feat: track name source (pubchem/cir) on ImageRecord"
```

---

### Task 4: PubChem + CIR network layer (`pipeline/namer.py`, part A)

This task replaces the OpenRouter implementation in `pipeline/namer.py` with the low-level HTTP functions only (no orchestration/cache yet — that's Task 5). The existing file's content is fully removed; `tests/test_namer.py` is fully rewritten (its current OpenRouter-mock tests no longer apply to anything in the codebase after this task).

**Files:**
- Modify: `pipeline/namer.py` (full rewrite)
- Modify: `tests/test_namer.py` (full rewrite)

**Interfaces:**
- Consumes: nothing new
- Produces: `pipeline.namer.NameLookupError` (public exception, subclass of `RuntimeError`)
- Produces: `pipeline.namer._RetriesExhausted` (internal exception)
- Produces: `pipeline.namer._pubchem_property(smiles: str, prop: str) -> str | None`
- Produces: `pipeline.namer._pubchem_synonyms(smiles: str) -> list[str]`
- Produces: `pipeline.namer._cir_iupac_name(smiles: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_namer.py` with:

```python
import pytest
import requests as req
from unittest.mock import MagicMock, patch
from pipeline.namer import _pubchem_property, _pubchem_synonyms, _cir_iupac_name, _RetriesExhausted


def _mock_response(status: int, text: str = "", headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.headers = headers or {}
    return resp


# --- _pubchem_property ---

def test_pubchem_property_success_returns_stripped_text():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "  ethanol  ")) as mock_req:
        result = _pubchem_property("CCO", "IUPACName")
    assert result == "ethanol"
    args, kwargs = mock_req.call_args
    assert args[0] == "POST"
    assert args[1] == "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/IUPACName/TXT"
    assert kwargs["data"] == {"smiles": "CCO"}


def test_pubchem_property_404_returns_none():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _pubchem_property("not_a_smiles", "IUPACName") is None


def test_pubchem_property_retries_503_then_succeeds(monkeypatch):
    monkeypatch.setattr("pipeline.namer.time.sleep", lambda _s: None)
    responses = [_mock_response(503, headers={"Retry-After": "1"}), _mock_response(200, "ethanol")]
    with patch("pipeline.namer.requests.request", side_effect=responses):
        result = _pubchem_property("CCO", "IUPACName")
    assert result == "ethanol"


def test_pubchem_property_exhausts_retries_raises():
    with patch("pipeline.namer.time.sleep"):
        with patch("pipeline.namer.requests.request", return_value=_mock_response(503)):
            with pytest.raises(_RetriesExhausted):
                _pubchem_property("CCO", "IUPACName")


def test_pubchem_property_network_error_retries_then_raises():
    with patch("pipeline.namer.time.sleep"):
        with patch("pipeline.namer.requests.request", side_effect=req.RequestException("timeout")):
            with pytest.raises(_RetriesExhausted):
                _pubchem_property("CCO", "IUPACName")


# --- _pubchem_synonyms ---

def test_pubchem_synonyms_success_returns_line_list():
    text = "2-acetyloxybenzoic acid\n2-Acetoxybenzoic acid\n50-78-2\n"
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, text)):
        result = _pubchem_synonyms("CC(=O)Oc1ccccc1C(=O)O")
    assert result == ["2-acetyloxybenzoic acid", "2-Acetoxybenzoic acid", "50-78-2"]


def test_pubchem_synonyms_404_returns_empty_list():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _pubchem_synonyms("not_a_smiles") == []


# --- _cir_iupac_name ---

def test_cir_iupac_name_success():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "ethanol")) as mock_req:
        result = _cir_iupac_name("CCO")
    assert result == "ethanol"
    args, kwargs = mock_req.call_args
    assert args[0] == "GET"
    assert args[1] == "https://cactus.nci.nih.gov/chemical/structure/CCO/iupac_name"


def test_cir_iupac_name_url_encodes_slash_characters():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "but-2-ene")) as mock_req:
        _cir_iupac_name("C/C=C/C")
    args, _ = mock_req.call_args
    assert "/" not in args[1].split("chemical/structure/")[1].split("/iupac_name")[0]


def test_cir_iupac_name_404_returns_none():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _cir_iupac_name("some_smiles") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_namer.py -v`
Expected: FAIL — old tests reference `lookup_iupac`/`lookup_trivial_name` with the old OpenRouter signature; new tests fail with `ImportError`.

- [ ] **Step 3: Write the implementation**

Replace the full contents of `pipeline/namer.py`:

```python
from __future__ import annotations
import time
import requests

_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CIR_BASE = "https://cactus.nci.nih.gov/chemical/structure"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class NameLookupError(RuntimeError):
    """All applicable sources failed after retries — distinct from a confirmed 'not found'."""


class _RetriesExhausted(Exception):
    pass


def _request_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.request(method, url, timeout=15, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))
            continue
        if resp.status_code in _RETRYABLE_STATUS:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else _BACKOFF_BASE_SECONDS * (2 ** attempt)
            time.sleep(min(wait, 30))
            last_exc = RuntimeError(f"{url} returned {resp.status_code}")
            continue
        return resp
    raise _RetriesExhausted(str(last_exc))


def _pubchem_property(smiles: str, prop: str) -> str | None:
    resp = _request_with_backoff(
        "POST", f"{_PUBCHEM_BASE}/compound/smiles/property/{prop}/TXT", data={"smiles": smiles}
    )
    return resp.text.strip() if resp.status_code == 200 else None


def _pubchem_synonyms(smiles: str) -> list[str]:
    resp = _request_with_backoff(
        "POST", f"{_PUBCHEM_BASE}/compound/smiles/synonyms/TXT", data={"smiles": smiles}
    )
    if resp.status_code != 200:
        return []
    return [line for line in resp.text.strip().splitlines() if line]


def _cir_iupac_name(smiles: str) -> str | None:
    encoded = requests.utils.quote(smiles, safe="")
    resp = _request_with_backoff("GET", f"{_CIR_BASE}/{encoded}/iupac_name")
    return resp.text.strip() if resp.status_code == 200 else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_namer.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/namer.py tests/test_namer.py
git commit -m "feat: replace OpenRouter naming with PubChem+CIR network layer"
```

---

### Task 5: Lookup orchestration + cache integration (`pipeline/namer.py`, part B)

**Files:**
- Modify: `pipeline/namer.py`
- Modify: `tests/test_namer.py`

**Interfaces:**
- Consumes: `pipeline.name_cache.get_cached`, `pipeline.name_cache.set_cached`, `pipeline.name_cache.DEFAULT_DB_PATH` (Task 2); `pipeline.salts.strip_to_parent` (Task 1); `_pubchem_property`, `_pubchem_synonyms`, `_cir_iupac_name`, `_RetriesExhausted`, `NameLookupError` (Task 4)
- Produces: `pipeline.namer.lookup_iupac(smiles: str) -> tuple[str | None, str]`
- Produces: `pipeline.namer.lookup_trivial_name(smiles: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_namer.py`:

```python
from pipeline.namer import lookup_iupac, lookup_trivial_name, NameLookupError
from pipeline.name_cache import get_cached


def test_lookup_iupac_pubchem_success(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "ethanol")):
        name, source = lookup_iupac("CCO")
    assert (name, source) == ("ethanol", "pubchem")
    assert get_cached("CCO", "iupac", "pubchem", db_path=tmp_path / "cache.db") == ("ethanol", True)


def test_lookup_iupac_uses_cache_on_second_call(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "ethanol")) as mock_req:
        lookup_iupac("CCO")
        lookup_iupac("CCO")
    assert mock_req.call_count == 1


def test_lookup_iupac_falls_back_to_cir_when_pubchem_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    responses = [_mock_response(404), _mock_response(200, "ethanol")]
    with patch("pipeline.namer.requests.request", side_effect=responses):
        name, source = lookup_iupac("CCO")
    assert (name, source) == ("ethanol", "cir")


def test_lookup_iupac_falls_back_to_cir_when_pubchem_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("pipeline.namer.time.sleep", lambda _s: None)
    responses = [_mock_response(503)] * 3 + [_mock_response(200, "ethanol")]
    with patch("pipeline.namer.requests.request", side_effect=responses):
        name, source = lookup_iupac("CCO")
    assert (name, source) == ("ethanol", "cir")


def test_lookup_iupac_raises_when_both_sources_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("pipeline.namer.time.sleep", lambda _s: None)
    with patch("pipeline.namer.requests.request", return_value=_mock_response(503)):
        with pytest.raises(NameLookupError):
            lookup_iupac("CCO")


def test_lookup_iupac_confirmed_not_found_in_both_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        name, source = lookup_iupac("XYZ")
    assert (name, source) == (None, "cir")


def test_lookup_iupac_strips_salts_before_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "acetate")) as mock_req:
        lookup_iupac("CC(=O)[O-].[Na+]")
    args, kwargs = mock_req.call_args
    assert kwargs["data"] == {"smiles": "CC(=O)[O-]"}


def test_lookup_trivial_name_returns_first_synonym(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    text = "2-acetyloxybenzoic acid\n2-Acetoxybenzoic acid\n50-78-2\n"
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, text)):
        result = lookup_trivial_name("CC(=O)Oc1ccccc1C(=O)O")
    assert result == "2-acetyloxybenzoic acid"


def test_lookup_trivial_name_no_synonyms_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert lookup_trivial_name("XYZ") is None


def test_lookup_trivial_name_raises_on_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr("pipeline.namer.time.sleep", lambda _s: None)
    with patch("pipeline.namer.requests.request", return_value=_mock_response(503)):
        with pytest.raises(NameLookupError):
            lookup_trivial_name("CCO")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_namer.py -v`
Expected: FAIL with `ImportError: cannot import name 'lookup_iupac'`

- [ ] **Step 3: Write the implementation**

Append to `pipeline/namer.py` (after the functions from Task 4):

```python
from pipeline.name_cache import get_cached, set_cached, DEFAULT_DB_PATH  # noqa: F401 (re-exported for monkeypatch target)
from pipeline.salts import strip_to_parent


def lookup_iupac(smiles: str) -> tuple[str | None, str]:
    canonical = strip_to_parent(smiles)
    cached = get_cached(canonical, "iupac", "pubchem", db_path=DEFAULT_DB_PATH)
    if cached is not None and cached[1]:
        return cached[0], "pubchem"

    pubchem_reachable = True
    if cached is None:
        try:
            name = _pubchem_property(canonical, "IUPACName")
        except _RetriesExhausted:
            pubchem_reachable = False
        else:
            set_cached(canonical, "iupac", "pubchem", name, db_path=DEFAULT_DB_PATH)
            if name is not None:
                return name, "pubchem"

    cached_cir = get_cached(canonical, "iupac", "cir", db_path=DEFAULT_DB_PATH)
    if cached_cir is not None:
        return (cached_cir[0], "cir") if cached_cir[1] else (None, "cir")

    try:
        name = _cir_iupac_name(canonical)
    except _RetriesExhausted as exc:
        reason = "PubChem and CIR both unreachable" if not pubchem_reachable else "CIR unreachable"
        raise NameLookupError(f"IUPAC lookup failed for {canonical}: {reason}") from exc

    set_cached(canonical, "iupac", "cir", name, db_path=DEFAULT_DB_PATH)
    return name, "cir"


def lookup_trivial_name(smiles: str) -> str | None:
    canonical = strip_to_parent(smiles)
    cached = get_cached(canonical, "trivial", "pubchem", db_path=DEFAULT_DB_PATH)
    if cached is not None:
        return cached[0] if cached[1] else None
    try:
        synonyms = _pubchem_synonyms(canonical)
    except _RetriesExhausted as exc:
        raise NameLookupError(f"Trivial name lookup failed for {canonical}: PubChem unreachable") from exc
    name = synonyms[0] if synonyms else None
    set_cached(canonical, "trivial", "pubchem", name, db_path=DEFAULT_DB_PATH)
    return name
```

Note: `DEFAULT_DB_PATH` is imported into `pipeline.namer`'s namespace specifically so tests can `monkeypatch.setattr("pipeline.namer.DEFAULT_DB_PATH", ...)` to redirect the cache to `tmp_path` — this mirrors how `pipeline.namer.requests` is monkeypatched, keeping all test isolation at the `pipeline.namer` module boundary.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_namer.py -v`
Expected: PASS (all tests from Task 4 and this task — 21 total)

- [ ] **Step 5: Commit**

```bash
git add pipeline/namer.py tests/test_namer.py
git commit -m "feat: orchestrate PubChem->CIR fallback and cache integration for name lookups"
```

---

### Task 6: Wire the worker to the new namer API (`gui/worker.py`)

**Files:**
- Modify: `gui/worker.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: `pipeline.namer.lookup_iupac(smiles) -> tuple[str | None, str]`, `pipeline.namer.lookup_trivial_name(smiles) -> str | None`, `pipeline.namer.NameLookupError` (Task 5); `ImageRecord.iupac_source` (Task 3)
- Produces: `RecognizerWorker` sets `record.iupac_name`, `record.iupac_source`, `record.trivial_name` using the new API

- [ ] **Step 1: Write the failing tests**

Replace the `lookup_iupac`/`lookup_trivial_name`-related tests in `tests/test_worker.py` (currently `tests/test_worker.py:29-58`, the OpenRouter-signature tests) with:

```python
def test_worker_logs_iupac_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles: ("benzene", "pubchem"))
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_sets_iupac_source_from_lookup(monkeypatch):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles: ("benzene", "cir"))

    records = [_make_record(prediction_types=["iupac"])]
    worker = RecognizerWorker(records, Config())
    result = {}
    worker.record_ready.connect(lambda r: result.setdefault("record", r))
    worker.run()

    assert result["record"].iupac_name == "benzene"
    assert result["record"].iupac_source == "cir"


def test_worker_emits_error_on_name_lookup_error(monkeypatch):
    from pipeline.namer import NameLookupError

    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))

    def _raise(smiles):
        raise NameLookupError("PubChem and CIR both unreachable")

    monkeypatch.setattr("pipeline.namer.lookup_iupac", _raise)

    errors = []
    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.error.connect(lambda msg: errors.append(msg))
    worker.run()

    assert any("IUPAC lookup failed" in e for e in errors)


def test_worker_logs_trivial_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", lambda smiles: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up common name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_emits_error_on_trivial_name_lookup_error(monkeypatch):
    from pipeline.namer import NameLookupError

    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))

    def _raise(smiles):
        raise NameLookupError("PubChem unreachable")

    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", _raise)

    errors = []
    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.error.connect(lambda msg: errors.append(msg))
    worker.run()

    assert any("Common name lookup failed" in e for e in errors)
```

Remove the now-obsolete `test_worker_passes_image_bytes_to_iupac_lookup` test (`tests/test_worker.py:60-70` in the current file) — naming lookups no longer take image bytes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`
Expected: FAIL — old code still calls `lookup_iupac(smiles, api_key, record.recognition_bytes)`.

- [ ] **Step 3: Update the implementation**

In `gui/worker.py`, replace lines 49–58 (the `if "iupac" in types and smiles:` block) and lines 60–69 (the `if "trivial" in types and smiles:` block):

```python
                    if "iupac" in types and smiles:
                        self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                        try:
                            log.debug("Looking up IUPAC name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.iupac_name, record.iupac_source = lookup_iupac(smiles)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.iupac_name, time.perf_counter() - t0)
                        except NameLookupError as exc:
                            log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                    if "trivial" in types and smiles:
                        self.status.emit(f"Looking up common name for {record.source_ref}…")
                        try:
                            log.debug("Looking up common name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.trivial_name = lookup_trivial_name(smiles)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.trivial_name, time.perf_counter() - t0)
                        except NameLookupError as exc:
                            log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")
```

Update the import at `gui/worker.py:27`:

```python
        from pipeline.namer import lookup_iupac, lookup_trivial_name, NameLookupError
```

The `api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key` line (`gui/worker.py:28`) is **kept** — `describe_image(record.recognition_bytes, api_key)` (`gui/worker.py:76`) still needs it for the unrelated "Describe Image" feature. Only the naming calls stop using it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/worker.py tests/test_worker.py
git commit -m "feat: wire RecognizerWorker to multi-source name lookup API"
```

---

### Task 7: Settings screen — availability badges (`gui/settings_dialog.py`)

**Files:**
- Modify: `gui/settings_dialog.py`

**Interfaces:**
- Consumes: `pipeline.namer._pubchem_property`, `pipeline.namer._cir_iupac_name` (Task 4, used for the availability ping)
- Produces: nothing new (UI integration only)

- [ ] **Step 1: Add the availability-check helper**

In `gui/settings_dialog.py`, add near the top (after `_dir_size_human`):

```python
def _check_pubchem_available() -> bool:
    from pipeline.namer import _pubchem_property
    try:
        return _pubchem_property("CCO", "IUPACName") is not None
    except Exception:
        return False


def _check_cir_available() -> bool:
    from pipeline.namer import _cir_iupac_name
    try:
        return _cir_iupac_name("CCO") is not None
    except Exception:
        return False
```

- [ ] **Step 2: Add the availability section, wired into `__init__`**

Add a new method, following the shape of `_build_openrouter_section`/`_build_model_info`:

```python
    def _build_naming_availability_section(self) -> QGroupBox:
        box = QGroupBox("Name Lookup Availability")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        avail_row = QHBoxLayout()
        self._pubchem_status = QLabel("○ Unknown")
        self._cir_status = QLabel("○ Unknown")
        avail_row.addWidget(QLabel("PubChem:"))
        avail_row.addWidget(self._pubchem_status)
        avail_row.addWidget(QLabel("CIR (fallback):"))
        avail_row.addWidget(self._cir_status)
        recheck_btn = QPushButton("Recheck")
        recheck_btn.clicked.connect(self._refresh_naming_availability)
        avail_row.addWidget(recheck_btn)
        avail_row.addStretch()
        vbox.addLayout(avail_row)

        note = QLabel(
            "IUPAC name lookups try PubChem first, then CIR automatically if PubChem is "
            "unavailable. This just shows current status — no action needed."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c757d; font-size: 11px;")
        vbox.addWidget(note)

        self._refresh_naming_availability()
        return box

    def _refresh_naming_availability(self) -> None:
        self._pubchem_status.setText("● Available" if _check_pubchem_available() else "● Unavailable")
        self._cir_status.setText("● Available" if _check_cir_available() else "● Unavailable")
```

Wire it into `__init__` (`gui/settings_dialog.py:85-90`), and narrow the OpenRouter section's note:

```python
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._build_openrouter_section())
        layout.addWidget(self._build_naming_availability_section())
        layout.addWidget(self._build_model_info())
        layout.addWidget(self._build_diagnostic_logging_section())
        layout.addWidget(buttons)
        self.setLayout(layout)
```

In `_build_openrouter_section` (`gui/settings_dialog.py:93-111`), update the note text:

```python
        note = QLabel(
            "Used for the \"Describe Image\" feature only. "
            "The OPENROUTER_API_KEY environment variable takes precedence if set."
        )
```

- [ ] **Step 3: Manual verification**

`gui/settings_dialog.py` has no existing dedicated unit test file, consistent with the rest of the GUI layer (it's exercised via the `run` skill / manual app launch, not `pytest`). Launch the app and confirm:
1. Settings opens; PubChem/CIR badges show a real status within a couple seconds.
2. "Recheck" re-runs the check.
3. OpenRouter section note now reads "Used for the 'Describe Image' feature only."

Run: `python -m pytest tests/ -v` to confirm no regressions in the rest of the suite.

- [ ] **Step 4: Commit**

```bash
git add gui/settings_dialog.py
git commit -m "feat: add PubChem/CIR availability badges to Settings"
```

---

### Task 8: Full suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass, including every test added in Tasks 1–6.

- [ ] **Step 2: Confirm no leftover references to the removed OpenRouter naming path**

Run: `grep -rn "lookup_iupac\|lookup_trivial_name" --include="*.py" . | grep -v node_modules | grep -v .venv`
Expected: Only matches in `pipeline/namer.py`, `gui/worker.py`, and `tests/test_namer.py`/`tests/test_worker.py` — no remaining references to the old `(smiles, api_key, image_bytes)` signature anywhere.

- [ ] **Step 3: Confirm no OpenRouter naming references remain in docs/comments**

Run: `grep -rn "OpenRouter\|openrouter" pipeline/namer.py gui/worker.py`
Expected: no output — the OpenRouter naming path is fully removed from these two files (OpenRouter usage elsewhere, e.g. `pipeline/describer.py`, is unrelated and untouched).
