# Offline Local Naming Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live PubChem/CIR naming path (`pipeline/namer.py`) with an offline, locally-stored PubChem dataset — an InChIKey-keyed SQLite index downloaded once (and refreshable) from Azure Blob Storage, with zero live-API fallback.

**Architecture:** `pipeline/name_dataset.py` owns the local SQLite file's path, readiness, and query. `pipeline/namer.py` computes an RDKit InChIKey from the recognized SMILES and queries it — no network calls at all. `gui/dataset_manager.py` (mirroring the existing `gui/model_manager.py` pattern) downloads and gunzips the dataset in a background `QThread`. `gui/settings_dialog.py` and `gui/file_picker.py` surface download/refresh UI and a first-run "not downloaded" banner.

**Tech Stack:** Python 3.9–3.12, `rdkit` (new), `pystow` (new explicit dependency — was previously only transitive via DECIMER), stdlib `sqlite3`/`gzip`, `requests` (already a dependency), PyQt6 `QThread`.

**Spec:** `docs/superpowers/specs/2026-08-30-offline-naming-dataset-design.md`

## Global Constraints

- No live-API fallback, anywhere: a confirmed dataset miss returns `None`. `NameLookupError` is raised only for an unparseable SMILES or a not-yet-downloaded dataset — never for "not found."
- Azure Blob Storage container name is `chem4all`; blob `naming_dataset.sqlite.gz` at the container root, anonymous public read (no auth in the download path).
- Dataset SQLite schema is a single table: `names(inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)`.
- Local dataset home is `pystow.join("chem4all", "naming")` — deliberately separate from DECIMER's `pystow.join("DECIMER-V2")` home.
- `pipeline/` must never import from `gui/` (existing one-way dependency direction in this codebase). `gui/dataset_manager.py` imports path/readiness helpers from `pipeline.name_dataset`, never the reverse.
- `rdkit` is pinned to `2026.3.4` (the version already installed and validated in this project's dev venv). `pystow` is added unpinned, matching this repo's existing convention of leaving all other `pyproject.toml` dependencies unpinned.
- Every module that reads dataset path/readiness state does so via `name_dataset.dataset_path()` / `name_dataset.is_dataset_ready()` (module-qualified access, i.e. `from pipeline import name_dataset` then `name_dataset.foo()`) rather than `from pipeline.name_dataset import dataset_path` — the qualified form is what makes `monkeypatch.setattr(name_dataset, "dataset_path", ...)` actually take effect in every consuming module. This bit both `gui/dataset_manager.py` and `pipeline/namer.py`; keep it this way in any new code that reads dataset state too.

---

### Task 1: Local dataset path, readiness, and query (`pipeline/name_dataset.py`)

**Files:**
- Create: `pipeline/name_dataset.py`
- Test: `tests/test_name_dataset.py`
- Modify: `pyproject.toml` (add `pystow` dependency)

**Interfaces:**
- Produces: `dataset_path() -> Path`
- Produces: `is_dataset_ready() -> bool`
- Produces: `lookup(inchikey: str, db_path: Path | None = None) -> tuple[str | None, str | None]` — raises `sqlite3.Error` if the dataset file is missing or unreadable.

- [ ] **Step 1: Add the `pystow` dependency**

In `pyproject.toml`, add `"pystow"` to the `dependencies` list (it was previously only pulled in transitively via DECIMER; `pipeline/name_dataset.py` now imports it directly, so it needs to be an explicit dependency):

```toml
dependencies = [
    "python-pptx",
    "python-docx",
    "Pillow",
    "PyQt6",
    "DECIMER",
    "cairosvg",
    "requests",
    "pystow",
]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_name_dataset.py`:

```python
import sqlite3
import pytest
from pipeline import name_dataset

ETHANOL_INCHIKEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def _make_fixture_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE names (inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)")
    conn.execute("INSERT INTO names VALUES (?, ?, ?)", (ETHANOL_INCHIKEY, "ethanol", "alcohol"))
    conn.commit()
    conn.close()


def test_dataset_path_uses_chem4all_naming_pystow_home(monkeypatch):
    monkeypatch.setattr("pipeline.name_dataset.pystow.join", lambda *parts: "/fake/home/" + "/".join(parts))
    assert str(name_dataset.dataset_path()) == "/fake/home/chem4all/naming/names.sqlite"


def test_is_dataset_ready_false_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    assert name_dataset.is_dataset_ready() is False


def test_is_dataset_ready_true_when_file_exists(tmp_path, monkeypatch):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: db)
    assert name_dataset.is_dataset_ready() is True


def test_lookup_returns_names_on_hit(tmp_path):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    assert name_dataset.lookup(ETHANOL_INCHIKEY, db_path=db) == ("ethanol", "alcohol")


def test_lookup_returns_none_none_on_miss(tmp_path):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    assert name_dataset.lookup("AAAAAAAAAAAAAA-AAAAAAAAAA-A", db_path=db) == (None, None)


def test_lookup_raises_when_dataset_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.sqlite"
    with pytest.raises(sqlite3.Error):
        name_dataset.lookup(ETHANOL_INCHIKEY, db_path=missing)


def test_lookup_raises_on_corrupt_dataset_file(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a real sqlite database")
    with pytest.raises(sqlite3.Error):
        name_dataset.lookup(ETHANOL_INCHIKEY, db_path=corrupt)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_name_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.name_dataset'`

- [ ] **Step 4: Write the implementation**

Create `pipeline/name_dataset.py`:

```python
from __future__ import annotations
import sqlite3
from pathlib import Path

import pystow


def dataset_path() -> Path:
    return Path(pystow.join("chem4all", "naming")) / "names.sqlite"


def is_dataset_ready() -> bool:
    return dataset_path().exists()


def lookup(inchikey: str, db_path: Path | None = None) -> tuple[str | None, str | None]:
    """Returns (iupac_name, trivial_name); both None if inchikey isn't in the dataset.
    Raises sqlite3.Error if the dataset file is missing or unreadable. Opened read-only
    so a missing file raises immediately instead of sqlite3 silently creating an empty
    database at that path."""
    path = db_path or dataset_path()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT iupac_name, trivial_name FROM names WHERE inchikey = ?",
            (inchikey,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return (None, None)
    return (row[0], row[1])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_name_dataset.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Install the new dependency and commit**

```bash
.venv/bin/pip install pystow
git add pipeline/name_dataset.py tests/test_name_dataset.py pyproject.toml
git commit -m "feat: add local naming dataset path/readiness/query layer"
```

---

### Task 2: Rewrite `pipeline/namer.py` around RDKit + the local dataset

This removes all live HTTP/retry code and the runtime query cache it depended on (`pipeline/name_cache.py`) — there is nothing left to cache once lookups are local SQLite reads.

**Files:**
- Modify: `pipeline/namer.py` (full rewrite)
- Modify: `tests/test_namer.py` (full rewrite)
- Delete: `pipeline/name_cache.py`
- Delete: `tests/test_name_cache.py`
- Modify: `pyproject.toml` (add `rdkit` dependency)

**Interfaces:**
- Consumes: `pipeline.name_dataset.is_dataset_ready`, `pipeline.name_dataset.lookup` (Task 1); `pipeline.salts.strip_to_parent` (existing)
- Produces: `pipeline.namer.NameLookupError` (public exception, subclass of `RuntimeError`) — raised only for unparseable SMILES or dataset-not-downloaded
- Produces: `pipeline.namer._inchikey_for(smiles: str) -> str`
- Produces: `pipeline.namer.lookup_iupac(smiles: str) -> str | None`
- Produces: `pipeline.namer.lookup_trivial_name(smiles: str) -> str | None`

- [ ] **Step 1: Add the `rdkit` dependency**

In `pyproject.toml`:

```toml
dependencies = [
    "python-pptx",
    "python-docx",
    "Pillow",
    "PyQt6",
    "DECIMER",
    "cairosvg",
    "requests",
    "pystow",
    "rdkit==2026.3.4",
]
```

- [ ] **Step 2: Delete the runtime name cache**

```bash
git rm pipeline/name_cache.py tests/test_name_cache.py
```

(There is no longer anything to cache — every lookup is now a local SQLite read, not a network round-trip. `pipeline/name_cache.py` was only ever used by the old live-API `pipeline/namer.py`, which this task fully replaces.)

- [ ] **Step 3: Write the failing tests**

Replace the full contents of `tests/test_namer.py` with:

```python
import pytest
from pipeline.namer import lookup_iupac, lookup_trivial_name, NameLookupError, _inchikey_for

ETHANOL_SMILES = "CCO"
ETHANOL_INCHIKEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


# --- _inchikey_for ---

def test_inchikey_for_computes_expected_key():
    assert _inchikey_for(ETHANOL_SMILES) == ETHANOL_INCHIKEY


def test_inchikey_for_strips_salts_before_computing():
    # Sodium acetate: without stripping the [Na+] fragment first, RDKit would compute
    # a different, salt-inclusive InChIKey that wouldn't match the parent compound's
    # entry in the dataset.
    assert _inchikey_for("CC(=O)[O-].[Na+]") == "QTBSBXVTEAMEQO-UHFFFAOYSA-M"


def test_inchikey_for_raises_on_unparseable_smiles():
    with pytest.raises(NameLookupError):
        _inchikey_for("not_a_smiles")


# --- lookup_iupac ---

def test_lookup_iupac_returns_name_on_hit(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: ("ethanol", "alcohol"))
    assert lookup_iupac(ETHANOL_SMILES) == "ethanol"


def test_lookup_iupac_returns_none_on_confirmed_miss(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: (None, None))
    assert lookup_iupac(ETHANOL_SMILES) is None


def test_lookup_iupac_raises_when_dataset_not_downloaded(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: False)
    with pytest.raises(NameLookupError):
        lookup_iupac(ETHANOL_SMILES)


def test_lookup_iupac_raises_on_unparseable_smiles(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    with pytest.raises(NameLookupError):
        lookup_iupac("not_a_smiles")


# --- lookup_trivial_name ---

def test_lookup_trivial_name_returns_name_on_hit(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: ("ethanol", "alcohol"))
    assert lookup_trivial_name(ETHANOL_SMILES) == "alcohol"


def test_lookup_trivial_name_returns_none_on_confirmed_miss(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: (None, None))
    assert lookup_trivial_name(ETHANOL_SMILES) is None


def test_lookup_trivial_name_raises_when_dataset_not_downloaded(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: False)
    with pytest.raises(NameLookupError):
        lookup_trivial_name(ETHANOL_SMILES)


# --- both call sites use the computed InChIKey, not the raw SMILES ---

def test_lookup_uses_computed_inchikey(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    calls = []

    def _fake_lookup(inchikey):
        calls.append(inchikey)
        return (None, None)

    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", _fake_lookup)
    lookup_iupac(ETHANOL_SMILES)
    assert calls == [ETHANOL_INCHIKEY]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_namer.py -v`
Expected: FAIL — old tests/implementation reference the removed HTTP functions and `name_cache`.

- [ ] **Step 5: Write the implementation**

Replace the full contents of `pipeline/namer.py`:

```python
from __future__ import annotations
from rdkit import Chem
from pipeline import name_dataset
from pipeline.salts import strip_to_parent


class NameLookupError(RuntimeError):
    """Unparseable SMILES, or the local dataset isn't downloaded yet — distinct
    from a confirmed 'not found', which returns None instead."""


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

Note: `from pipeline import name_dataset` (not `from pipeline.name_dataset import is_dataset_ready, lookup`) is deliberate — see the Global Constraints note on why the module-qualified form is required for `monkeypatch.setattr` to work here and in Task 5.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_namer.py -v`
Expected: PASS (11 tests)

- [ ] **Step 7: Install the new dependency and commit**

```bash
.venv/bin/pip install "rdkit==2026.3.4"
git add pipeline/namer.py tests/test_namer.py pyproject.toml
git commit -m "feat: replace live PubChem/CIR naming with local RDKit+dataset lookup"
```

---

### Task 3: Remove `ImageRecord.iupac_source`

With a single local dataset, there's no second source to distinguish — this field (added when the design had PubChem vs. CIR as two distinguishable sources) is removed outright, not repurposed.

**Files:**
- Modify: `models/image_record.py`
- Modify: `tests/test_image_record.py`

**Interfaces:**
- Produces: `ImageRecord` without an `iupac_source` field; `to_review_dict()`/`from_review_dict()` no longer read or write it.

- [ ] **Step 1: Remove the obsolete tests**

In `tests/test_image_record.py`, delete these three test functions from the end of the file (currently lines 209–234):

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

The file should end with `test_result_lines_returns_decorative_placeholder` (currently lines 198–206).

- [ ] **Step 2: Run tests to verify the remaining suite still passes and the field is still referenced**

Run: `python -m pytest tests/test_image_record.py -v`
Expected: PASS (the three deleted tests are gone; nothing yet fails since the field still exists).

- [ ] **Step 3: Remove the field from the implementation**

In `models/image_record.py`, remove line 18:

```python
    iupac_source: str | None = None  # 'pubchem' | 'cir'
```

In `to_review_dict()`, remove the line:

```python
            "iupac_source": self.iupac_source,
```

In `from_review_dict()`, remove the line:

```python
            iupac_source=d.get("iupac_source"),
```

`result_lines()` needs no change — it never referenced `iupac_source`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_image_record.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "refactor: remove ImageRecord.iupac_source (single naming source now)"
```

---

### Task 4: Update the worker call site (`gui/worker.py`)

**Files:**
- Modify: `gui/worker.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: `pipeline.namer.lookup_iupac(smiles) -> str | None`, `pipeline.namer.lookup_trivial_name(smiles) -> str | None`, `pipeline.namer.NameLookupError` (Task 2); `ImageRecord` without `iupac_source` (Task 3)
- Produces: `RecognizerWorker` sets `record.iupac_name` and `record.trivial_name` only (no more `record.iupac_source`)

- [ ] **Step 1: Write the updated tests**

Replace the full contents of `tests/test_worker.py`:

```python
from __future__ import annotations
import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from config import Config
from models.image_record import ImageRecord
from gui.worker import RecognizerWorker


def _make_record(prediction_types=None):
    return ImageRecord(
        id="r1",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"fake_image",
        prediction_types=prediction_types or ["smiles"],
    )


def test_worker_logs_recognizing_and_result(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record()], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Recognizing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> SMILES 'C1=CC=CC=C1'") for m in messages)


def test_worker_logs_iupac_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_emits_error_on_name_lookup_error(monkeypatch):
    from pipeline.namer import NameLookupError

    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))

    def _raise(smiles):
        raise NameLookupError("Naming dataset not downloaded — see Settings.")

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
        raise NameLookupError("Naming dataset not downloaded — see Settings.")

    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", _raise)

    errors = []
    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.error.connect(lambda msg: errors.append(msg))
    worker.run()

    assert any("Common name lookup failed" in e for e in errors)


def test_worker_logs_description(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["description"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Describing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'A benzene ring diagram.'") for m in messages)


def test_worker_handles_multiple_prediction_types_in_one_record(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles: "benzene")
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    record = _make_record(prediction_types=["iupac", "description"])
    ready_records = []
    worker = RecognizerWorker([record], Config())
    worker.record_ready.connect(ready_records.append)
    worker.run()

    assert record.predicted_smiles == "C1=CC=CC=C1"
    assert record.iupac_name == "benzene"
    assert record.trivial_name is None
    assert record.description == "A benzene ring diagram."
    assert len(ready_records) == 1


def test_worker_does_not_process_decorative_record(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "gui.worker._run_decimer",
        lambda *args, **kwargs: calls.append("decimer") or ("C", 1.0),
    )
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda *args, **kwargs: calls.append("describe") or "some description",
    )

    record = _make_record(prediction_types=["decorative"])
    ready_records = []
    worker = RecognizerWorker([record], Config())
    worker.record_ready.connect(ready_records.append)
    worker.run()

    assert calls == []
    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.iupac_name is None
    assert record.trivial_name is None
    assert record.description is None
    assert len(ready_records) == 1
    assert ready_records[0] is record


def test_worker_emits_status_for_decorative_record():
    record = _make_record(prediction_types=["decorative"])
    statuses = []
    worker = RecognizerWorker([record], Config())
    worker.status.connect(statuses.append)
    worker.run()

    assert len(statuses) == 1
    assert "slide 1, shape 1" in statuses[0]
```

(This drops `test_worker_sets_iupac_source_from_lookup` entirely — Task 3 removed the field it asserted on — and updates the two `lookup_iupac` mocks from `lambda smiles: ("benzene", "pubchem")` to `lambda smiles: "benzene"` to match the new plain-`str | None` signature.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`
Expected: FAIL — `gui/worker.py:54` still does `record.iupac_name, record.iupac_source = lookup_iupac(smiles)`, which now raises `TypeError` (`lookup_iupac` returns a plain string, not a 2-tuple) and references the removed `iupac_source` attribute.

- [ ] **Step 3: Update the implementation**

In `gui/worker.py`, replace line 54:

```python
                            record.iupac_name, record.iupac_source = lookup_iupac(smiles)
```

with:

```python
                            record.iupac_name = lookup_iupac(smiles)
```

Everything else in `gui/worker.py` is unchanged — the import at line 27 (`from pipeline.namer import lookup_iupac, lookup_trivial_name, NameLookupError`) still imports the same three names, and `record.recognition_bytes`/`api_key` handling for the unrelated "Describe Image" feature is untouched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/worker.py tests/test_worker.py
git commit -m "refactor: update RecognizerWorker for single-value lookup_iupac return"
```

---

### Task 5: Dataset download worker (`gui/dataset_manager.py`)

**Files:**
- Create: `gui/dataset_manager.py`
- Test: `tests/test_dataset_manager.py`

**Interfaces:**
- Consumes: `pipeline.name_dataset.dataset_path`, `pipeline.name_dataset.is_dataset_ready` (Task 1)
- Produces: `DATASET_URL: str`
- Produces: `dataset_last_downloaded() -> datetime | None`
- Produces: `DatasetDownloadWorker(QThread)` with `status(str)`, `progress(int, int)`, `finished()`, `error(str)` signals

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dataset_manager.py`:

```python
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone
from pipeline import name_dataset
from gui import dataset_manager


def test_dataset_last_downloaded_returns_none_when_no_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    assert dataset_manager.dataset_last_downloaded() is None


def test_dataset_last_downloaded_parses_sidecar_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    ts = datetime(2026, 8, 12, 9, 30, tzinfo=timezone.utc)
    (tmp_path / "names.sqlite.meta").write_text(f"{ts.isoformat()}\nhttps://example/foo.gz\n")
    assert dataset_manager.dataset_last_downloaded() == ts


def test_dataset_last_downloaded_returns_none_on_corrupt_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    (tmp_path / "names.sqlite.meta").write_text("not-a-timestamp\n")
    assert dataset_manager.dataset_last_downloaded() is None
```

(`DatasetDownloadWorker` itself is exercised only manually/by inspection in Task 7 — this matches how `ModelDownloadWorker` in `gui/model_manager.py`, the pattern it mirrors, also has no dedicated download-path unit test in `tests/test_model_manager.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dataset_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.dataset_manager'`

- [ ] **Step 3: Write the implementation**

Create `gui/dataset_manager.py`:

```python
from __future__ import annotations
import gzip
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from pipeline import name_dataset

log = logging.getLogger(__name__)

DATASET_URL = "https://<account>.blob.core.windows.net/chem4all/naming_dataset.sqlite.gz"


def _meta_path() -> Path:
    target = name_dataset.dataset_path()
    return target.with_suffix(target.suffix + ".meta")


def dataset_last_downloaded() -> datetime | None:
    meta = _meta_path()
    if not meta.exists():
        return None
    try:
        return datetime.fromisoformat(meta.read_text().splitlines()[0].strip())
    except (ValueError, IndexError):
        return None


class DatasetDownloadWorker(QThread):
    status = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # bytes_done, total_bytes
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            import requests
        except ImportError:
            self.error.emit("'requests' package not found — run: pip install requests")
            return

        target = name_dataset.dataset_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        self.status.emit("Downloading naming dataset…")
        try:
            self._download(requests, target)
        except Exception as exc:
            self.error.emit(f"Failed to download naming dataset: {exc}")
            return

        self.finished.emit()

    def _download(self, requests, target: Path) -> None:
        gz_path = target.with_suffix(target.suffix + ".gz.part")
        resp = requests.get(DATASET_URL, stream=True, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))

        downloaded = 0
        with open(gz_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)

        self.status.emit("Extracting naming dataset…")
        self.progress.emit(0, 0)  # switch to indeterminate during extraction
        tmp_sqlite = target.with_suffix(target.suffix + ".part")
        with gzip.open(gz_path, "rb") as src, open(tmp_sqlite, "wb") as dst:
            shutil.copyfileobj(src, dst)
        gz_path.unlink(missing_ok=True)
        tmp_sqlite.replace(target)  # atomic on the same filesystem

        _meta_path().write_text(f"{datetime.now(timezone.utc).isoformat()}\n{DATASET_URL}\n")
```

Note: `_meta_path()` and `_download()` call `name_dataset.dataset_path()` (module-qualified), not a directly-imported `dataset_path` name — this is what lets `monkeypatch.setattr(name_dataset, "dataset_path", ...)` in the tests actually take effect here (see Global Constraints).

The `<account>` placeholder in `DATASET_URL` is a known open item from the design spec (the Azure Storage account name hasn't been provisioned/chosen yet) — fill it in once it exists; nothing else in this task depends on the real value.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dataset_manager.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/dataset_manager.py tests/test_dataset_manager.py
git commit -m "feat: add naming dataset download worker"
```

---

### Task 6: Settings dialog — remove diagnostic badges, add Naming Dataset section

**Files:**
- Modify: `gui/settings_dialog.py`

**Interfaces:**
- Consumes: `pipeline.name_dataset.dataset_path`, `pipeline.name_dataset.is_dataset_ready` (Task 1); `gui.dataset_manager.dataset_last_downloaded`, `gui.dataset_manager.DatasetDownloadWorker` (Task 5)
- Produces: nothing new (UI integration only)

- [ ] **Step 1: Remove the live-availability diagnostic UI**

In `gui/settings_dialog.py`, delete:
- `_check_pubchem_available()` (lines 26–31)
- `_check_cir_available()` (lines 34–39)
- `_NamingAvailabilityCheckWorker` (lines 42–48)
- the `_build_naming_availability_section()` call at line 114 and its definition (lines 143–170)
- `_refresh_naming_availability()` (lines 172–180)
- `_on_naming_availability_checked()` (lines 182–184)
- the worker-cleanup block in `done()` (lines 273–276), i.e. remove:

```python
    def done(self, result: int) -> None:
        worker = getattr(self, "_naming_availability_worker", None)
        if worker is not None and worker.isRunning():
            worker.quit()
            worker.wait()
        super().done(result)
```

There's nothing left to "check" — dataset presence is a synchronous file check, not a network probe. (`done()` itself can be removed entirely if nothing else in the class overrides it — confirm before deleting the method vs. just its body.)

- [ ] **Step 2: Add the Naming Dataset section**

Add a new method, in the same style as `_build_model_info()`:

```python
    def _build_naming_dataset_section(self) -> QGroupBox:
        from pipeline.name_dataset import dataset_path, is_dataset_ready
        from gui.dataset_manager import dataset_last_downloaded

        box = QGroupBox("Naming Dataset")
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        ready = is_dataset_ready()
        last_downloaded = dataset_last_downloaded()
        if ready and last_downloaded is not None:
            status_text = f"✓  Downloaded  (last updated: {last_downloaded:%Y-%m-%d})"
            status_color = "#155724"
        elif ready:
            status_text = "✓  Downloaded"
            status_color = "#155724"
        else:
            status_text = "✗  Not downloaded"
            status_color = "#721c24"

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self._dataset_status_label = QLabel(status_text)
        self._dataset_status_label.setStyleSheet(f"color: {status_color}; font-weight: bold;")
        status_row.addWidget(self._dataset_status_label)
        status_row.addStretch()
        vbox.addLayout(status_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Location:"))
        path_edit = QLineEdit(str(dataset_path().parent))
        path_edit.setReadOnly(True)
        path_row.addWidget(path_edit)
        show_btn = QPushButton("Show in Finder")
        show_btn.setEnabled(dataset_path().parent.exists())
        show_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(dataset_path().parent)))
        )
        path_row.addWidget(show_btn)
        vbox.addLayout(path_row)

        self._dataset_refresh_btn = QPushButton("Refresh Dataset" if ready else "Download Dataset")
        self._dataset_refresh_btn.clicked.connect(self._start_dataset_download)
        vbox.addWidget(self._dataset_refresh_btn)

        self._dataset_progress_bar = QProgressBar()
        self._dataset_progress_bar.setTextVisible(False)
        self._dataset_progress_bar.hide()
        vbox.addWidget(self._dataset_progress_bar)

        note = QLabel(
            "IUPAC and trivial names are looked up from a local offline dataset. "
            "No internet connection is required."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #6c757d; font-size: 11px;")
        vbox.addWidget(note)

        self._dataset_download_worker = None
        return box

    def _start_dataset_download(self) -> None:
        if self._dataset_download_worker is not None and self._dataset_download_worker.isRunning():
            return
        from gui.dataset_manager import DatasetDownloadWorker

        self._dataset_refresh_btn.setEnabled(False)
        self._dataset_progress_bar.setRange(0, 0)
        self._dataset_progress_bar.show()

        worker = DatasetDownloadWorker()
        worker.status.connect(self._dataset_status_label.setText)
        worker.progress.connect(self._on_dataset_progress)
        worker.finished.connect(self._on_dataset_download_finished)
        worker.error.connect(self._on_dataset_download_error)
        self._dataset_download_worker = worker
        worker.start()

    def _on_dataset_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._dataset_progress_bar.setRange(0, 100)
            self._dataset_progress_bar.setValue(int(done * 100 / total))
        else:
            self._dataset_progress_bar.setRange(0, 0)

    def _on_dataset_download_finished(self) -> None:
        from pipeline.name_dataset import dataset_path
        from gui.dataset_manager import dataset_last_downloaded

        self._dataset_progress_bar.hide()
        self._dataset_refresh_btn.setEnabled(True)
        self._dataset_refresh_btn.setText("Refresh Dataset")
        last_downloaded = dataset_last_downloaded()
        suffix = f"  (last updated: {last_downloaded:%Y-%m-%d})" if last_downloaded else ""
        self._dataset_status_label.setText(f"✓  Downloaded{suffix}")
        self._dataset_status_label.setStyleSheet("color: #155724; font-weight: bold;")

    def _on_dataset_download_error(self, msg: str) -> None:
        self._dataset_progress_bar.hide()
        self._dataset_refresh_btn.setEnabled(True)
        QMessageBox.warning(self, "Naming Dataset", f"Could not download the naming dataset: {msg}")
```

Wire it into `__init__` in place of the removed availability section:

```python
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self._build_openrouter_section())
        layout.addWidget(self._build_naming_dataset_section())
        layout.addWidget(self._build_model_info())
        layout.addWidget(self._build_diagnostic_logging_section())
        layout.addWidget(buttons)
        self.setLayout(layout)
```

Add a `done()` override that cleans up the dataset worker the same way the old one cleaned up the availability worker:

```python
    def done(self, result: int) -> None:
        worker = getattr(self, "_dataset_download_worker", None)
        if worker is not None and worker.isRunning():
            worker.quit()
            worker.wait()
        super().done(result)
```

- [ ] **Step 3: Manual verification**

`gui/settings_dialog.py` has no dedicated unit test file (consistent with the rest of the GUI layer — it's exercised via the `run` skill / manual app launch, not `pytest`). Launch the app and confirm:
1. Settings opens; the "Naming Dataset" section shows "✗ Not downloaded" (assuming a fresh dev environment with no dataset yet).
2. Clicking "Download Dataset" attempts a real download against `DATASET_URL` — expected to fail cleanly with a `QMessageBox.warning` until the real Azure account name replaces the `<account>` placeholder (Task 5's known open item). Confirm it fails *gracefully* (no crash, button re-enabled) rather than confirming the download itself succeeds.
3. The old PubChem/CIR availability badges are gone from Settings.

Run: `python -m pytest tests/ -v` to confirm no regressions in the rest of the suite.

- [ ] **Step 4: Commit**

```bash
git add gui/settings_dialog.py
git commit -m "feat: replace naming availability badges with Naming Dataset download UI"
```

---

### Task 7: First-run "dataset missing" banner (`gui/file_picker.py`)

**Files:**
- Modify: `gui/file_picker.py`

**Interfaces:**
- Consumes: `pipeline.name_dataset.is_dataset_ready` (Task 1); `gui.dataset_manager.DatasetDownloadWorker` (Task 5)
- Produces: nothing new (UI integration only)

- [ ] **Step 1: Add a second worker slot and the new banner**

In `__init__` (`gui/file_picker.py:19`), add a slot for the dataset worker next to the existing model-download worker:

```python
        self._download_worker = None
        self._dataset_download_worker = None
```

After the existing model banner is added to the layout (`gui/file_picker.py:28-29`), add the dataset banner:

```python
        self._model_banner = self._build_model_banner()
        layout.addWidget(self._model_banner)

        self._dataset_banner = self._build_dataset_banner()
        layout.addWidget(self._dataset_banner)
```

At the end of `__init__`, where model readiness is checked (`gui/file_picker.py:73-75`), add the same check for the dataset:

```python
        from gui.model_manager import is_model_ready
        if is_model_ready():
            self._model_banner.hide()

        from pipeline.name_dataset import is_dataset_ready
        if is_dataset_ready():
            self._dataset_banner.hide()
```

- [ ] **Step 2: Implement `_build_dataset_banner()` and its download handlers**

Add a new method, mirroring `_build_model_banner()`'s structure and styling:

```python
    def _build_dataset_banner(self) -> QFrame:
        banner = QFrame()
        banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner.setStyleSheet(
            "QFrame { background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; }"
        )

        vbox = QVBoxLayout(banner)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(6)

        self._dataset_status_label = QLabel(
            "⚠  Naming dataset not downloaded. "
            "IUPAC and common name lookups will not work until the dataset is installed. "
            "Click the button below to download it."
        )
        self._dataset_status_label.setWordWrap(True)
        self._dataset_status_label.setStyleSheet("QLabel { color: #664d03; }")
        vbox.addWidget(self._dataset_status_label)

        self._dataset_progress_bar = QProgressBar()
        self._dataset_progress_bar.setRange(0, 100)
        self._dataset_progress_bar.setTextVisible(True)
        self._dataset_progress_bar.hide()
        vbox.addWidget(self._dataset_progress_bar)

        self._dataset_bytes_label = QLabel()
        self._dataset_bytes_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._dataset_bytes_label.setStyleSheet("QLabel { color: #664d03; }")
        self._dataset_bytes_label.hide()
        vbox.addWidget(self._dataset_bytes_label)

        self._dataset_download_btn = QPushButton("Download Naming Dataset")
        self._dataset_download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dataset_download_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffce3a, stop:1 #ffc107);"
            "  color: #212529; border: 1px solid #d39e00; border-bottom: 2px solid #b38600;"
            "  border-radius: 6px; padding: 8px 16px; font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffd65c, stop:1 #ffcd39);"
            "}"
            "QPushButton:pressed {"
            "  background: #e0a800; border: 1px solid #b38600; border-bottom: 1px solid #b38600;"
            "  padding-top: 9px; padding-bottom: 7px;"
            "}"
            "QPushButton:disabled { background: #ffe69c; color: #8a6d1f; border: 1px solid #ffe69c; }"
        )
        self._dataset_download_btn.clicked.connect(self._start_dataset_download)
        vbox.addWidget(self._dataset_download_btn)

        return banner

    def _start_dataset_download(self) -> None:
        from gui.dataset_manager import DatasetDownloadWorker
        self._dataset_download_btn.setEnabled(False)
        self._dataset_download_btn.setText("Downloading…")
        self._dataset_progress_bar.show()
        self._dataset_bytes_label.show()
        self._open_btn.setEnabled(False)

        self._dataset_download_worker = DatasetDownloadWorker()
        self._dataset_download_worker.status.connect(self._dataset_status_label.setText)
        self._dataset_download_worker.progress.connect(self._on_dataset_download_progress)
        self._dataset_download_worker.finished.connect(self._on_dataset_download_finished)
        self._dataset_download_worker.error.connect(self._on_dataset_download_error)
        self._dataset_download_worker.start()

    def _on_dataset_download_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._dataset_progress_bar.setRange(0, 100)
            self._dataset_progress_bar.setValue(int(done * 100 / total))
            done_mb = done / 1_048_576
            total_mb = total / 1_048_576
            self._dataset_bytes_label.setText(f"{done_mb:.1f} / {total_mb:.1f} MB")
        else:
            self._dataset_progress_bar.setRange(0, 0)
            self._dataset_bytes_label.clear()

    def _on_dataset_download_finished(self) -> None:
        self._cleanup_dataset_download_worker()
        self._dataset_banner.hide()
        self._open_btn.setEnabled(True)

    def _on_dataset_download_error(self, msg: str) -> None:
        self._cleanup_dataset_download_worker()
        self._dataset_status_label.setText(f"⚠  Download failed: {msg}")
        self._dataset_progress_bar.hide()
        self._dataset_bytes_label.hide()
        self._dataset_download_btn.setText("Retry Download")
        self._dataset_download_btn.setEnabled(True)
        self._open_btn.setEnabled(True)

    def _cleanup_dataset_download_worker(self) -> None:
        if self._dataset_download_worker is None:
            return
        self._dataset_download_worker.wait()
        self._dataset_download_worker = None
```

- [ ] **Step 3: Guard window close during a dataset download**

Update `closeEvent()` (`gui/file_picker.py:135-144`) to also block closing during a dataset download:

```python
    def closeEvent(self, event: QCloseEvent) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            QMessageBox.information(
                self,
                "Download in Progress",
                "Please wait for the DECIMER model download to finish before closing chem4all.",
            )
            event.ignore()
            return
        if self._dataset_download_worker is not None and self._dataset_download_worker.isRunning():
            QMessageBox.information(
                self,
                "Download in Progress",
                "Please wait for the naming dataset download to finish before closing chem4all.",
            )
            event.ignore()
            return
        super().closeEvent(event)
```

- [ ] **Step 4: Manual verification**

`tests/test_file_picker.py` has no existing test asserting on `_model_banner`'s visibility/`is_model_ready()` interaction either — matching that precedent, this task adds no new automated test for banner visibility, only the implementation. Run the full existing suite to confirm no regressions, then launch the app manually and confirm:
1. On a fresh environment (no dataset downloaded), both the DECIMER-missing and dataset-missing banners show simultaneously.
2. Clicking "Download Naming Dataset" shows progress UI and (until the real Azure account name is filled in) fails gracefully with a clear error and a "Retry Download" button.
3. Attempting to close the window mid-download shows the "Download in Progress" dialog and blocks the close.

Run: `python -m pytest tests/test_file_picker.py -v`
Expected: PASS (all existing tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add gui/file_picker.py
git commit -m "feat: add first-run naming-dataset-missing banner"
```

---

### Task 8: Build script (`pipeline/build_dataset.py`)

Maintainer/CI-run tool, not part of the shipped app and not run against real PubChem bulk data in CI — per the design spec, this is verified by manual inspection rather than `pytest` (it operates on multi-GB external downloads).

**Files:**
- Create: `pipeline/build_dataset.py`

**Interfaces:**
- Produces (as a runnable script, not an importable API other tasks depend on): `python -m pipeline.build_dataset [--work-dir DIR] [--output FILE]`, which writes a `naming_dataset.sqlite.gz` matching the `names(inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)` schema Task 1 expects.

- [ ] **Step 1: Write the implementation**

Create `pipeline/build_dataset.py`:

```python
from __future__ import annotations
# Maintainer tool: builds the local naming dataset SQLite index from PubChem's
# bulk data files, for upload to Azure Blob Storage. Not run by the shipped
# app — see docs/superpowers/specs/2026-08-30-offline-naming-dataset-design.md.
#
# Usage: python -m pipeline.build_dataset [--work-dir DIR] [--output FILE]
import argparse
import gzip
import logging
import sqlite3
from pathlib import Path
from urllib.request import urlopen

log = logging.getLogger(__name__)

_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras"
_INCHIKEY_URL = f"{_BASE_URL}/CID-InChI-Key.gz"
_IUPAC_URL = f"{_BASE_URL}/CID-IUPAC.gz"
_SYNONYM_URL = f"{_BASE_URL}/CID-Synonym-filtered.gz"


def _download(url: str, dest: Path) -> None:
    log.info("Downloading %s -> %s", url, dest)
    with urlopen(url) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)


def _iter_tsv(path: Path):
    """Yields (cid, rest) from a CID-sorted, gzip'd TSV bulk file."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts or not parts[0]:
                continue
            yield int(parts[0]), parts[1:]


def _first_synonym_per_cid(synonym_path: Path):
    """CID-Synonym-filtered.gz has multiple rows per CID in relevance order;
    yields only the first (most relevant) synonym per CID."""
    last_cid = None
    for cid, rest in _iter_tsv(synonym_path):
        if cid == last_cid:
            continue
        last_cid = cid
        if rest and rest[0]:
            yield cid, rest[0]


def merge_by_cid(inchikey_path: Path, iupac_path: Path, synonym_path: Path):
    """Linear merge-join of the three CID-sorted bulk files, restricted to CIDs
    present in synonym_path (compounds with at least one known synonym).
    Yields (inchikey, iupac_name, trivial_name) rows; iupac_name is None if
    PubChem has no computed IUPAC name for that CID; a CID with no InChIKey
    at all is skipped (nothing to index it by)."""
    inchikey_rows = _iter_tsv(inchikey_path)             # (cid, [inchi, inchikey])
    iupac_rows = _iter_tsv(iupac_path)                   # (cid, [iupac_name])
    synonym_rows = _first_synonym_per_cid(synonym_path)  # (cid, first_synonym)

    ik_cid, ik_rest = next(inchikey_rows, (None, None))
    iu_cid, iu_rest = next(iupac_rows, (None, None))

    for syn_cid, trivial_name in synonym_rows:
        while ik_cid is not None and ik_cid < syn_cid:
            ik_cid, ik_rest = next(inchikey_rows, (None, None))
        while iu_cid is not None and iu_cid < syn_cid:
            iu_cid, iu_rest = next(iupac_rows, (None, None))

        if ik_cid != syn_cid:
            continue
        inchikey = ik_rest[-1]
        iupac_name = iu_rest[0] if iu_cid == syn_cid and iu_rest else None
        yield inchikey, iupac_name, trivial_name


def build_index(rows, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE names (inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)"
        )
        # OR IGNORE: if PubChem publishes more than one CID for the same InChIKey
        # (e.g. isotope/stereo variants that collapse to one standard InChIKey),
        # keep whichever row was inserted first rather than raising.
        conn.executemany(
            "INSERT OR IGNORE INTO names (inchikey, iupac_name, trivial_name) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def gzip_file(src: Path, dest: Path) -> None:
    with open(src, "rb") as f_in, gzip.open(dest, "wb") as f_out:
        while chunk := f_in.read(1 << 20):
            f_out.write(chunk)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Build the offline naming dataset SQLite index from PubChem bulk data."
    )
    parser.add_argument("--work-dir", type=Path, default=Path("build_dataset_work"))
    parser.add_argument("--output", type=Path, default=Path("naming_dataset.sqlite.gz"))
    args = parser.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    inchikey_path = args.work_dir / "CID-InChI-Key.gz"
    iupac_path = args.work_dir / "CID-IUPAC.gz"
    synonym_path = args.work_dir / "CID-Synonym-filtered.gz"
    db_path = args.work_dir / "names.sqlite"

    for url, dest in (
        (_INCHIKEY_URL, inchikey_path),
        (_IUPAC_URL, iupac_path),
        (_SYNONYM_URL, synonym_path),
    ):
        if not dest.exists():
            _download(url, dest)

    log.info("Joining bulk files by CID...")
    rows = merge_by_cid(inchikey_path, iupac_path, synonym_path)
    build_index(rows, db_path)

    log.info("Compressing %s -> %s", db_path, args.output)
    gzip_file(db_path, args.output)
    log.info("Done: %s", args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual verification**

This step requires downloading real multi-GB PubChem bulk files — do not run it in CI. As the maintainer:

1. Run `python -m pipeline.build_dataset --work-dir /tmp/build_dataset_work` and let it download all three bulk files (this will take a while and use significant disk space).
2. Once it completes, spot-check the output:
   ```bash
   gunzip -k naming_dataset.sqlite.gz
   sqlite3 naming_dataset.sqlite "SELECT COUNT(*) FROM names;"
   sqlite3 naming_dataset.sqlite "SELECT * FROM names WHERE inchikey = 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N';"  # ethanol
   ```
   Confirm the ethanol row returns `("LFQSCWFLJHTTHZ-UHFFFAOYSA-N", "ethanol", <some trivial name>)` and the row count is well under the ~119M full-universe figure (the synonym-filter subset from the design spec's Context section).
3. Per the design spec's open caveat: measure the actual compressed size of `naming_dataset.sqlite.gz` at this point and compare against the full-universe estimate (~3.85 GB) — if it isn't meaningfully smaller, flag this back against the design spec's filter criteria before publishing it to Azure Storage.

- [ ] **Step 3: Commit**

```bash
git add pipeline/build_dataset.py
git commit -m "feat: add maintainer build script for the offline naming dataset"
```

---

### Task 9: Full suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass, including every test added or modified in Tasks 1–7.

- [ ] **Step 2: Confirm no leftover references to the removed live-API naming path**

Run: `grep -rn "PUBCHEM_BASE\|CIR_BASE\|_pubchem_property\|_pubchem_synonyms\|_cir_iupac_name\|_RetriesExhausted\|name_cache\|iupac_source" --include="*.py" . | grep -v .venv`
Expected: no output — every reference to the old live-API naming architecture and the removed `iupac_source` field is gone.

- [ ] **Step 3: Confirm the new modules don't import from `gui/` in `pipeline/`**

Run: `grep -rn "^from gui\|^import gui" pipeline/*.py`
Expected: no output — `pipeline/` stays free of any `gui/` import, per the Global Constraints layering rule.
