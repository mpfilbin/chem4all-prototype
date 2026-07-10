# Multi-Prediction Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users request multiple prediction types (SMILES, IUPAC Name, Common Name, Describe Image) per image in the Select Images modal, show all results for an image on separate lines in the Review view, and lock each Review row's result field read-only until that image's own predictions have all returned.

**Architecture:** `ImageRecord.prediction_type: str` becomes `prediction_types: list[str]`. The worker computes the union of whatever stages are implied by the selected types for a record, then emits `record_ready` once per record after all its stages finish — this single emission is the exact signal the Review window already needs to unlock that row. The Select modal swaps its per-row radio group for independent checkboxes plus a validation banner.

**Tech Stack:** Python 3.9–3.12, PyQt6, pytest (widgets tested with `QT_QPA_PLATFORM=offscreen` + a real `QApplication` instance, no pytest-qt dependency).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-10-multi-prediction-selection-design.md` (read before starting if anything below is unclear).
- Python compatibility: `requires-python = ">=3.9,<3.13"` (`pyproject.toml`) — keep using `from __future__ import annotations` in any file that uses `list[str]` / `X | None` syntax, matching existing files.
- Result values are joined with `"\n\n"` (a full blank line) between each prediction's value, raw values only, no per-type labels.
- No backward compatibility for old single-`prediction_type` review JSON files — breaking the on-disk format is acceptable.
- Selection modal: SMILES checkbox starts checked; IUPAC Name, Common Name, Describe Image start unchecked (matches today's default).
- Selection modal validation: if any *included* row (its leftmost "include" checkbox checked) has zero prediction-type checkboxes checked, disable "Identify Selected" and show an error banner reading exactly `"Each selected image needs at least one prediction type checked."`, styled dark-red-on-light-red (`color: #721c24; background: #f8d7da;`) consistent with the existing status-banner pattern in `gui/review_window.py`.
- Review view field label becomes the fixed string `"Prediction Results:"` (replacing the old per-type `_TYPE_LABELS` lookup).
- Review row edit-lock is per-image: a row unlocks as soon as that image's own `record_ready` fires, independent of other rows/pages still processing.
- Prev/Next/Accept navigation in the Review window stays gated on the whole batch finishing — unchanged, out of scope.

---

### Task 1: `ImageRecord` — multi-type field and composed result lines

**Files:**
- Modify: `models/image_record.py`
- Test: `tests/test_image_record.py`

**Interfaces:**
- Produces: `ImageRecord.prediction_types: list[str]` (default `["smiles"]`), `ImageRecord.result_lines() -> list[str]` (ordered `smiles → iupac → trivial → description`, only entries whose type is in `prediction_types` and whose backing field is truthy), `to_review_dict()`/`from_review_dict()` using the `"prediction_types"` JSON key (a list).

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_image_record.py` with:

```python
from models.image_record import ImageRecord


def test_image_record_defaults():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
    )
    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.iupac_name is None
    assert record.trivial_name is None
    assert record.approved_value is None
    assert record.is_chemical is None
    assert record.description is None
    assert record.prediction_types == ["smiles"]


def test_image_record_to_review_dict_excludes_bytes():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        iupac_name="benzene",
        trivial_name="benzene",
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    assert "thumbnail_bytes" not in d
    assert "recognition_bytes" not in d
    assert d["id"] == "abc123"
    assert d["predicted_smiles"] == "C1=CC=CC=C1"
    assert d["iupac_name"] == "benzene"
    assert d["trivial_name"] == "benzene"
    assert d["approved_value"] == "C1=CC=CC=C1"
    assert d["is_chemical"] is True
    assert d["description"] is None
    assert d["prediction_types"] == ["smiles"]


def test_image_record_from_review_dict_roundtrip():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        iupac_name="benzene",
        trivial_name="benzene",
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    restored = ImageRecord.from_review_dict(d)
    assert restored.id == record.id
    assert restored.iupac_name == "benzene"
    assert restored.trivial_name == "benzene"
    assert restored.approved_value == record.approved_value
    assert restored.thumbnail_bytes == b""
    assert restored.recognition_bytes == b""
    assert restored.description is None
    assert restored.prediction_types == ["smiles"]


def test_image_record_prediction_types_default():
    record = ImageRecord(
        id="x",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )
    assert record.prediction_types == ["smiles"]


def test_result_lines_returns_smiles_by_default():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        prediction_types=["smiles"],
    )
    assert record.result_lines() == ["C1=CC=CC=C1"]


def test_result_lines_returns_iupac_name():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        iupac_name="benzene",
        prediction_types=["iupac"],
    )
    assert record.result_lines() == ["benzene"]


def test_result_lines_returns_trivial_name():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        trivial_name="benzene",
        prediction_types=["trivial"],
    )
    assert record.result_lines() == ["benzene"]


def test_result_lines_skips_type_when_name_not_yet_loaded():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        prediction_types=["iupac"],  # iupac_name not set yet
    )
    assert record.result_lines() == []


def test_image_record_description_default():
    record = ImageRecord(
        id="x",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )
    assert record.description is None


def test_result_lines_returns_description():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        description="Diagram of ATP synthase embedded in the inner mitochondrial membrane.",
        prediction_types=["description"],
    )
    assert record.result_lines() == [
        "Diagram of ATP synthase embedded in the inner mitochondrial membrane."
    ]


def test_result_lines_skips_description_when_not_yet_loaded():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        prediction_types=["description"],  # description not set yet
    )
    assert record.result_lines() == []


def test_result_lines_returns_multiple_types_in_fixed_order():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        iupac_name="benzene",
        description="A benzene ring diagram.",
        prediction_types=["description", "smiles", "iupac"],  # list order shouldn't matter
    )
    assert record.result_lines() == [
        "C1=CC=CC=C1",
        "benzene",
        "A benzene ring diagram.",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_image_record.py -v`
Expected: FAIL — `AttributeError`/`TypeError` referencing `prediction_types` and `result_lines` not existing yet (the old `prediction_type`/`result_value` API is still in place).

- [ ] **Step 3: Implement the model change**

Replace the full contents of `models/image_record.py` with:

```python
from __future__ import annotations
from dataclasses import dataclass, field

_TYPE_ORDER = ["smiles", "iupac", "trivial", "description"]


@dataclass
class ImageRecord:
    id: str
    source_ref: str
    thumbnail_bytes: bytes
    recognition_bytes: bytes
    predicted_smiles: str | None = None
    confidence: float | None = None
    iupac_name: str | None = None
    trivial_name: str | None = None
    description: str | None = None
    prediction_types: list[str] = field(default_factory=lambda: ["smiles"])
    approved_value: str | None = None
    is_chemical: bool | None = None

    def result_lines(self) -> list[str]:
        field_for_type = {
            "smiles": self.predicted_smiles,
            "iupac": self.iupac_name,
            "trivial": self.trivial_name,
            "description": self.description,
        }
        return [
            field_for_type[t]
            for t in _TYPE_ORDER
            if t in self.prediction_types and field_for_type[t]
        ]

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "iupac_name": self.iupac_name,
            "trivial_name": self.trivial_name,
            "description": self.description,
            "prediction_types": self.prediction_types,
            "approved_value": self.approved_value,
            "is_chemical": self.is_chemical,
        }

    @classmethod
    def from_review_dict(cls, d: dict) -> ImageRecord:
        return cls(
            id=d["id"],
            source_ref=d["source_ref"],
            thumbnail_bytes=b"",
            recognition_bytes=b"",
            predicted_smiles=d.get("predicted_smiles"),
            confidence=d.get("confidence"),
            iupac_name=d.get("iupac_name"),
            trivial_name=d.get("trivial_name"),
            description=d.get("description"),
            prediction_types=d.get("prediction_types", ["smiles"]),
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_image_record.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Run the reviewer tests to confirm no collateral breakage**

Run: `pytest tests/test_reviewer.py -v`
Expected: PASS — `pipeline/reviewer.py` uses `to_review_dict`/`from_review_dict` generically and never references `prediction_type`, so it needs no code changes.

- [ ] **Step 6: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "$(cat <<'EOF'
Replace ImageRecord.prediction_type with a multi-type list

Support requesting several prediction types for one image at once.
result_lines() replaces result_value(), returning every populated
type's value in a fixed order instead of picking exactly one.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Worker — run the union of selected prediction stages per record

**Files:**
- Modify: `gui/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `ImageRecord.prediction_types: list[str]` (Task 1).
- Produces: `RecognizerWorker.run()` behavior — for each record, runs DECIMER if `smiles`/`iupac`/`trivial` is requested, runs the IUPAC/trivial lookups independently (not `elif`) when both are requested, runs `describe_image` if `description` is requested, and emits exactly one `record_ready` per record after all its requested stages have been attempted.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_worker.py` with:

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
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_logs_trivial_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up common name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


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
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key: "benzene")
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
```

- [ ] **Step 2: Run tests to verify the new test fails**

Run: `pytest tests/test_worker.py -v`
Expected: `test_worker_handles_multiple_prediction_types_in_one_record` FAILs (worker still branches on a single `record.prediction_type`, so `record.iupac_name` stays `None` since `prediction_types` isn't read at all yet); the other four tests currently pass unchanged since single-type behavior is intact, but will start failing once Step 3 lands if Step 3 is done incorrectly — re-run after Step 3 regardless.

- [ ] **Step 3: Implement the worker change**

Replace the `run` method in `gui/worker.py` (keep the imports, `log`, class fields, and `__init__` unchanged):

```python
    def run(self) -> None:
        from pipeline.describer import describe_image
        from pipeline.namer import lookup_iupac, lookup_trivial_name
        api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
        total = len(self._records)
        for i, record in enumerate(self._records):
            types = set(record.prediction_types)
            try:
                if types & {"smiles", "iupac", "trivial"}:
                    self.status.emit(f"Identifying {record.source_ref}  ({i + 1} of {total})…")
                    smiles = None
                    try:
                        log.debug("Recognizing %s...", record.source_ref)
                        t0 = time.perf_counter()
                        smiles, confidence = _run_decimer(record.recognition_bytes)
                        log.debug("%s -> SMILES '%s' (%.2fs)", record.source_ref, smiles, time.perf_counter() - t0)
                        record.predicted_smiles = smiles
                        record.confidence = confidence
                    except Exception as exc:
                        log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Could not identify {record.source_ref}: {exc}")
                        record.predicted_smiles = None
                        record.confidence = None

                    if "iupac" in types and smiles:
                        self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                        try:
                            log.debug("Looking up IUPAC name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.iupac_name = lookup_iupac(smiles, api_key)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.iupac_name, time.perf_counter() - t0)
                        except Exception as exc:
                            log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                    if "trivial" in types and smiles:
                        self.status.emit(f"Looking up common name for {record.source_ref}…")
                        try:
                            log.debug("Looking up common name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.trivial_name = lookup_trivial_name(smiles, api_key)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.trivial_name, time.perf_counter() - t0)
                        except Exception as exc:
                            log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

                if "description" in types:
                    self.status.emit(f"Describing {record.source_ref}  ({i + 1} of {total})…")
                    try:
                        log.debug("Describing %s...", record.source_ref)
                        t0 = time.perf_counter()
                        record.description = describe_image(record.recognition_bytes, api_key)
                        log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.description, time.perf_counter() - t0)
                    except Exception as exc:
                        log.warning("Description failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Could not describe {record.source_ref}: {exc}")
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worker.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/worker.py tests/test_worker.py
git commit -m "$(cat <<'EOF'
Run the union of selected prediction stages per record

A record can now request SMILES, IUPAC, Common Name, and/or
Describe Image together; the worker runs whichever stages are
implied and still emits record_ready exactly once per record.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Selection window — multi-select checkboxes and zero-type validation

**Files:**
- Modify: `gui/selection_window.py`
- Test: `tests/test_selection_window.py` (new)

**Interfaces:**
- Consumes: `ImageRecord.prediction_types` (Task 1).
- Produces: `_SelectionRow.prediction_types -> list[str]` (checked types in fixed order `smiles, iupac, trivial→"trivial", description`), `_SelectionRow.connect_changed(slot)` (wires the include checkbox and all 4 type checkboxes to one revalidation slot), `SelectionWindow._error_banner: QLabel` (hidden unless an included row has zero types checked), `SelectionWindow._start_identification()` sets `record.prediction_types = row.prediction_types` (a list, not a string) on every included record.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_selection_window.py`:

```python
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from config import Config
from models.image_record import ImageRecord
from gui.selection_window import SelectionWindow

_app = QApplication.instance() or QApplication(sys.argv)


def _make_record(id="r1"):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )


def test_selection_row_defaults_to_smiles_only():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    assert window._rows[0].prediction_types == ["smiles"]


def test_selection_row_reports_multiple_checked_types():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._iupac_check.setChecked(True)
    row._describe_check.setChecked(True)
    assert row.prediction_types == ["smiles", "iupac", "description"]


def test_identify_button_disabled_when_included_row_has_no_types():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._smiles_check.setChecked(False)
    assert window._identify_btn.isEnabled() is False
    assert window._error_banner.isVisible() is True


def test_identify_button_enabled_when_all_included_rows_have_types():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False


def test_error_banner_ignores_excluded_rows_with_no_types():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    row2 = window._rows[1]
    row2.checkbox.setChecked(False)
    row2._smiles_check.setChecked(False)
    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False


def test_start_identification_sets_prediction_types_on_selected_records(monkeypatch):
    monkeypatch.setattr("gui.review_window.ReviewWindow.show", lambda self: None)
    monkeypatch.setattr("gui.review_window.ReviewWindow.raise_", lambda self: None)
    monkeypatch.setattr("gui.review_window.ReviewWindow.activateWindow", lambda self: None)
    monkeypatch.setattr("gui.worker.RecognizerWorker.start", lambda self: None)

    record = _make_record()
    window = SelectionWindow([record], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._iupac_check.setChecked(True)

    window._start_identification()

    assert record.prediction_types == ["smiles", "iupac"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection_window.py -v`
Expected: FAIL with `AttributeError` — `_SelectionRow` still exposes radio buttons and a single `prediction_type` property, and `SelectionWindow` has no `_error_banner`.

- [ ] **Step 3: Implement the selection window change**

Replace the full contents of `gui/selection_window.py` with:

```python
from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy,
)
from config import Config
from models.image_record import ImageRecord
from gui.widgets import ThumbnailLabel


class SelectionWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._rows: list[_SelectionRow] = []

        self.setWindowTitle(f"Select Images — {source_path.name}")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QLabel(
            f"<b>{len(records)} image(s) found.</b> "
            "Select which to send for chemical structure identification."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._error_banner = QLabel()
        self._error_banner.setWordWrap(True)
        self._error_banner.setStyleSheet(
            "QLabel { background: #f8d7da; color: #721c24; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._error_banner.setVisible(False)
        layout.addWidget(self._error_banner)

        sel_row = QHBoxLayout()
        all_btn = QPushButton("Select All")
        none_btn = QPushButton("Select None")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(4)

        for record in records:
            row = _SelectionRow(record)
            row.connect_changed(self._update_identify_btn)
            self._rows.append(row)
            container_layout.addWidget(row)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        footer = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        self._identify_btn = QPushButton()
        self._identify_btn.clicked.connect(self._start_identification)
        footer.addWidget(cancel_btn)
        footer.addStretch()
        footer.addWidget(self._identify_btn)
        layout.addLayout(footer)

        self._update_identify_btn()

    def _set_all(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)

    def _update_identify_btn(self) -> None:
        n = sum(1 for row in self._rows if row.checkbox.isChecked())
        has_invalid_row = any(
            row.checkbox.isChecked() and not row.prediction_types
            for row in self._rows
        )
        if has_invalid_row:
            self._error_banner.setText(
                "Each selected image needs at least one prediction type checked."
            )
            self._error_banner.setVisible(True)
            self._identify_btn.setEnabled(False)
        else:
            self._error_banner.setVisible(False)
            self._identify_btn.setEnabled(n > 0)
        self._identify_btn.setText(f"Identify Selected ({n})  →")

    def _start_identification(self) -> None:
        from gui.review_window import ReviewWindow
        from gui.worker import RecognizerWorker

        selected = []
        for row in self._rows:
            if row.checkbox.isChecked():
                row.record.prediction_types = row.prediction_types
                selected.append(row.record)

        self._review_window = ReviewWindow(selected, self._config, self._source_path)
        self._worker = RecognizerWorker(selected, self._config)
        self._worker.record_ready.connect(self._review_window.on_record_ready)
        self._worker.status.connect(self._review_window.on_recognition_status)
        self._worker.finished.connect(self._review_window.on_recognition_finished)
        self._worker.error.connect(self._review_window.on_recognition_error)
        self._worker.start()

        self.hide()
        self._review_window.show()
        self._review_window.raise_()
        self._review_window.activateWindow()


class _SelectionRow(QFrame):
    def __init__(self, record: ImageRecord) -> None:
        super().__init__()
        self.record = record
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Include in identification")
        layout.addWidget(self.checkbox)

        thumb = ThumbnailLabel(record, size=64)
        thumb.setFixedSize(72, 72)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumb)

        ref = QLabel(record.source_ref)
        ref.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(ref)

        self._smiles_check = QCheckBox("SMILES")
        self._iupac_check = QCheckBox("IUPAC Name")
        self._trivial_check = QCheckBox("Common Name")
        self._describe_check = QCheckBox("Describe Image")
        self._smiles_check.setChecked(True)
        for box in (self._smiles_check, self._iupac_check, self._trivial_check, self._describe_check):
            layout.addWidget(box)

    @property
    def prediction_types(self) -> list[str]:
        types = []
        if self._smiles_check.isChecked():
            types.append("smiles")
        if self._iupac_check.isChecked():
            types.append("iupac")
        if self._trivial_check.isChecked():
            types.append("trivial")
        if self._describe_check.isChecked():
            types.append("description")
        return types

    def connect_changed(self, slot) -> None:
        self.checkbox.stateChanged.connect(slot)
        self._smiles_check.stateChanged.connect(slot)
        self._iupac_check.stateChanged.connect(slot)
        self._trivial_check.stateChanged.connect(slot)
        self._describe_check.stateChanged.connect(slot)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection_window.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "$(cat <<'EOF'
Allow selecting multiple prediction types per image

Replace the per-row radio group with independent checkboxes for
SMILES, IUPAC Name, Common Name, and Describe Image, and block
Identify with an error banner if an included row has none checked.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Review window — composed multi-line text and per-image edit lock

**Files:**
- Modify: `gui/review_window.py`
- Test: `tests/test_review_window.py` (new)

**Interfaces:**
- Consumes: `ImageRecord.result_lines()` (Task 1), `record.id` uniqueness across the batch.
- Produces: `_RecordRow(record, done: bool)` constructor signature; `_RecordRow.update_record(record)` now also unlocks a previously-locked row; `ReviewWindow._done_ids: set[str]` tracking which records have fully returned.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_review_window.py`:

```python
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtWidgets import QApplication

from config import Config
from models.image_record import ImageRecord
from gui.review_window import ReviewWindow, _RecordRow

_app = QApplication.instance() or QApplication(sys.argv)


def _make_record(id="r1", **kwargs):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        **kwargs,
    )


def test_record_row_locked_while_not_done():
    record = _make_record()
    row = _RecordRow(record, done=False)
    assert row._value_field.isReadOnly() is True
    assert row._value_field.toPlainText() == ""
    assert row._restore_btn.isVisible() is False


def test_record_row_editable_and_populated_when_done():
    record = _make_record(
        predicted_smiles="CCO",
        iupac_name="ethanol",
        prediction_types=["smiles", "iupac"],
    )
    row = _RecordRow(record, done=True)
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO\n\nethanol"


def test_update_record_unlocks_row_and_fills_composed_text():
    record = _make_record(prediction_types=["smiles", "description"])
    row = _RecordRow(record, done=False)

    record.predicted_smiles = "CCO"
    record.description = "A clear liquid in a flask."
    row.update_record(record)

    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO\n\nA clear liquid in a flask."


def test_review_window_on_record_ready_unlocks_visible_row(tmp_path):
    record = _make_record(prediction_types=["smiles"])
    window = ReviewWindow([record], Config(), tmp_path / "sample.pptx")
    row = window._rows[0]
    assert row._value_field.isReadOnly() is True

    record.predicted_smiles = "CCO"
    window.on_record_ready(record)

    assert record.id in window._done_ids
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "CCO"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review_window.py -v`
Expected: FAIL with `TypeError: __init__() missing 1 required positional argument: 'done'` (current `_RecordRow` takes only `record`) and `AttributeError` on `window._done_ids`.

- [ ] **Step 3: Implement the review window change**

In `gui/review_window.py`, delete the `_TYPE_LABELS` dict (lines 16–20) entirely.

Replace the `_RecordRow` class with:

```python
class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, done: bool, parent=None):
        super().__init__(parent)
        self._record = record
        self._done = done
        self._edited = False

        layout = QHBoxLayout()

        self._thumb = ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel("Prediction Results:"))
        self._value_field = QTextEdit()
        self._value_field.setPlaceholderText("Awaiting result…")
        self._value_field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        metrics = self._value_field.fontMetrics()
        frame = self._value_field.frameWidth() * 2
        self._value_field.setFixedHeight(metrics.lineSpacing() * 4 + frame + 12)

        if done:
            composed = "\n\n".join(record.result_lines())
            initial_text = record.approved_value if record.approved_value is not None else composed
            self._value_field.setPlainText(initial_text)
            self._edited = initial_text != composed
        else:
            self._value_field.setReadOnly(True)

        self._value_field.textChanged.connect(self._on_text_changed)
        info.addWidget(self._value_field)

        self._restore_btn = QPushButton("↺ Restore predicted value")
        self._restore_btn.clicked.connect(self._restore_predicted)
        info.addWidget(self._restore_btn)
        self._update_restore_visibility()

        layout.addLayout(info)
        self.setLayout(layout)

    def _set_field_text(self, text: str) -> None:
        self._value_field.blockSignals(True)
        self._value_field.setPlainText(text)
        self._value_field.blockSignals(False)
        self._update_restore_visibility()

    def _on_text_changed(self) -> None:
        self._edited = True
        self._update_restore_visibility()

    def _update_restore_visibility(self) -> None:
        if not self._done:
            self._restore_btn.setVisible(False)
            return
        predicted = "\n\n".join(self._record.result_lines())
        self._restore_btn.setVisible(self._value_field.toPlainText().strip() != predicted)

    def _restore_predicted(self) -> None:
        self._set_field_text("\n\n".join(self._record.result_lines()))
        self._edited = False

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._thumb.update_record(record)
        was_done = self._done
        self._done = True
        if not was_done:
            self._value_field.setReadOnly(False)
        if not self._edited:
            self._set_field_text("\n\n".join(record.result_lines()))

    def apply_to_record(self) -> None:
        value = self._value_field.toPlainText().strip()
        self._record.approved_value = value
        self._record.is_chemical = bool(value)
```

In `ReviewWindow.__init__`, add `self._done_ids: set[str] = set()` next to the existing `self._error_count = 0` / `self._recognition_done = False` lines.

In `ReviewWindow._render_page`, change the row-construction line from:

```python
        for record in self._page_records():
            row = _RecordRow(record)
            self._rows.append(row)
            self._grid.addWidget(row)
```

to:

```python
        for record in self._page_records():
            row = _RecordRow(record, done=record.id in self._done_ids)
            self._rows.append(row)
            self._grid.addWidget(row)
```

In `ReviewWindow.on_record_ready`, add the id to `_done_ids` before updating the row:

```python
    def on_record_ready(self, record: ImageRecord) -> None:
        self._recognized += 1
        self._done_ids.add(record.id)
        for row in self._rows:
            if row._record.id == record.id:
                row.update_record(record)
                break
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review_window.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/review_window.py tests/test_review_window.py
git commit -m "$(cat <<'EOF'
Lock Review result fields until all of an image's predictions return

Each row now starts read-only and unlocks the moment its own
record_ready fires, independent of other rows still processing.
The field shows every requested prediction's value, blank-line
separated, under a generic "Prediction Results:" label.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: All tests pass, including the new `tests/test_selection_window.py` and `tests/test_review_window.py`, and every pre-existing test file (`test_config.py`, `test_describer.py`, `test_extractor.py`, `test_logging_setup.py`, `test_main.py`, `test_model_manager.py`, `test_namer.py`, `test_pipeline_integration.py`, `test_recognizer.py`, `test_reviewer.py`, `test_writer.py`).

- [ ] **Step 2: Grep for any leftover references to the old single-type API**

Run: `grep -rn "prediction_type\b\|result_value\|_TYPE_LABELS" gui/ models/ pipeline/ tests/`
Expected: no matches (the word-boundary `\b` after `prediction_type` excludes the new `prediction_types`).

If this finds anything, it's a leftover reference to the old API that Tasks 1–4 missed — fix it before considering the plan done.
