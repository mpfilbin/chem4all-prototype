# Prediction Type Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move prediction type choice (SMILES / IUPAC / Common Name) to the Select Images screen so the worker runs the full pipeline automatically and the Review screen shows only the final result plus a custom override.

**Architecture:** Each `_SelectionRow` gains radio buttons; `_start_identification` stamps `record.prediction_type` before handing off to `RecognizerWorker`, which now runs the optional name-lookup step inline after SMILES recognition. `_RecordRow` in the Review screen is simplified to a single result field + override.

**Tech Stack:** PyQt6, pipeline.namer (lookup_iupac / lookup_trivial_name already implemented), pipeline.recognizer (_run_decimer)

## Global Constraints

- Python 3.9–3.12 (no 3.13+)
- PyQt6 for all GUI; no other Qt bindings
- `prediction_type` values are the strings `"smiles"`, `"iupac"`, `"trivial"` — no enums
- `gui/namer_worker.py` is deleted in Task 4; it must not be referenced after that point

---

### Task 1: ImageRecord — add `prediction_type` field and `result_value()` method

**Files:**
- Modify: `models/image_record.py`
- Modify: `tests/test_image_record.py`

**Interfaces:**
- Produces: `ImageRecord.prediction_type: str = "smiles"`, `ImageRecord.result_value() -> str | None`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_image_record.py`:

```python
def test_image_record_prediction_type_default():
    record = ImageRecord(
        id="x", source_ref="slide 1, shape 1",
        thumbnail_bytes=b"", recognition_bytes=b"",
    )
    assert record.prediction_type == "smiles"


def test_result_value_returns_smiles_by_default():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1", prediction_type="smiles",
    )
    assert record.result_value() == "C1=CC=CC=C1"


def test_result_value_returns_iupac_name():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        iupac_name="benzene", prediction_type="iupac",
    )
    assert record.result_value() == "benzene"


def test_result_value_returns_trivial_name():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        trivial_name="benzene", prediction_type="trivial",
    )
    assert record.result_value() == "benzene"


def test_result_value_returns_none_when_name_not_yet_loaded():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        prediction_type="iupac",  # iupac_name not set yet
    )
    assert record.result_value() is None
```

Also update the three existing tests to include `prediction_type`:

In `test_image_record_defaults`: add `assert record.prediction_type == "smiles"`

In `test_image_record_to_review_dict_excludes_bytes`: add `assert d["prediction_type"] == "smiles"`

In `test_image_record_from_review_dict_roundtrip`: add `assert restored.prediction_type == "smiles"`

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_image_record.py -v
```
Expected: failures on the new tests (AttributeError: prediction_type)

- [ ] **Step 3: Implement changes in `models/image_record.py`**

Replace the entire file with:

```python
from __future__ import annotations
from dataclasses import dataclass


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
    prediction_type: str = "smiles"
    approved_value: str | None = None
    is_chemical: bool | None = None

    def result_value(self) -> str | None:
        if self.prediction_type == "iupac":
            return self.iupac_name
        if self.prediction_type == "trivial":
            return self.trivial_name
        return self.predicted_smiles

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "iupac_name": self.iupac_name,
            "trivial_name": self.trivial_name,
            "prediction_type": self.prediction_type,
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
            prediction_type=d.get("prediction_type", "smiles"),
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_image_record.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "feat: add prediction_type field and result_value() to ImageRecord"
```

---

### Task 2: SelectionWindow — per-row prediction type radio buttons

**Files:**
- Modify: `gui/selection_window.py`

**Interfaces:**
- Consumes: `ImageRecord.prediction_type` (from Task 1)
- Produces: `_SelectionRow.prediction_type -> str` property; `_start_identification` stamps `record.prediction_type` before handing off

- [ ] **Step 1: Update imports in `gui/selection_window.py`**

Change the QtWidgets import to add `QRadioButton` and `QButtonGroup`:

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy,
    QRadioButton, QButtonGroup,
)
```

- [ ] **Step 2: Replace `_SelectionRow` class**

```python
class _SelectionRow(QFrame):
    def __init__(self, record: ImageRecord) -> None:
        super().__init__()
        self.record = record
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        thumb = ThumbnailLabel(record, size=64)
        thumb.setFixedSize(72, 72)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumb)

        ref = QLabel(record.source_ref)
        ref.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(ref)

        self._smiles_radio = QRadioButton("SMILES")
        self._iupac_radio = QRadioButton("IUPAC Name")
        self._trivial_radio = QRadioButton("Common Name")
        self._type_group = QButtonGroup(self)
        for btn in (self._smiles_radio, self._iupac_radio, self._trivial_radio):
            self._type_group.addButton(btn)
            layout.addWidget(btn)
        self._smiles_radio.setChecked(True)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setToolTip("Include in identification")
        layout.addWidget(self.checkbox)

    @property
    def prediction_type(self) -> str:
        if self._iupac_radio.isChecked():
            return "iupac"
        if self._trivial_radio.isChecked():
            return "trivial"
        return "smiles"
```

- [ ] **Step 3: Update `_start_identification` to stamp `prediction_type`**

Replace the existing `_start_identification` method:

```python
def _start_identification(self) -> None:
    from gui.review_window import ReviewWindow
    from gui.worker import RecognizerWorker

    selected = []
    for row in self._rows:
        if row.checkbox.isChecked():
            row.record.prediction_type = row.prediction_type
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
```

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v
```
Expected: all existing tests pass

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py
git commit -m "feat: add per-image prediction type radio buttons to SelectionWindow"
```

---

### Task 3: RecognizerWorker — run name lookup after SMILES recognition

**Files:**
- Modify: `gui/worker.py`

**Interfaces:**
- Consumes: `ImageRecord.prediction_type` (Task 1), `lookup_iupac`, `lookup_trivial_name` from `pipeline.namer`, `Config.openrouter_api_key`
- Produces: `record.iupac_name` or `record.trivial_name` set before `record_ready` is emitted

- [ ] **Step 1: Replace `gui/worker.py` with updated implementation**

```python
from __future__ import annotations
import logging
import os
from PyQt6.QtCore import QThread, pyqtSignal
from config import Config
from models.image_record import ImageRecord
from pipeline.recognizer import _run_decimer

log = logging.getLogger(__name__)


class RecognizerWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    record_ready = pyqtSignal(object)  # ImageRecord
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, records: list[ImageRecord], config: Config) -> None:
        super().__init__()
        self._records = records
        self._config = config

    def run(self) -> None:
        from pipeline.namer import lookup_iupac, lookup_trivial_name
        api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
        total = len(self._records)
        for i, record in enumerate(self._records):
            self.status.emit(f"Identifying {record.source_ref}  ({i + 1} of {total})…")
            try:
                smiles, confidence = _run_decimer(record.recognition_bytes)
                record.predicted_smiles = smiles
                record.confidence = confidence

                if record.prediction_type == "iupac" and smiles:
                    self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                    try:
                        record.iupac_name = lookup_iupac(smiles, api_key)
                    except Exception as exc:
                        log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                elif record.prediction_type == "trivial" and smiles:
                    self.status.emit(f"Looking up common name for {record.source_ref}…")
                    try:
                        record.trivial_name = lookup_trivial_name(smiles, api_key)
                    except Exception as exc:
                        log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

            except Exception as exc:
                log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                self.error.emit(f"Could not identify {record.source_ref}: {exc}")
                record.predicted_smiles = None
                record.confidence = None
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add gui/worker.py
git commit -m "feat: RecognizerWorker runs IUPAC/trivial name lookup after SMILES recognition"
```

---

### Task 4: ReviewWindow — simplify _RecordRow and remove namer_worker.py

**Files:**
- Modify: `gui/review_window.py`
- Delete: `gui/namer_worker.py`

**Interfaces:**
- Consumes: `ImageRecord.result_value()` (Task 1), `ImageRecord.prediction_type` (Task 1)

- [ ] **Step 1: Replace `gui/review_window.py`**

```python
from __future__ import annotations
import math
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit,
    QMessageBox,
)
from config import Config
from models.image_record import ImageRecord
from pipeline.writer import write
from gui.widgets import ThumbnailLabel

_TYPE_LABELS = {
    "iupac": "IUPAC Name:",
    "trivial": "Common Name:",
}


class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, parent=None):
        super().__init__(parent)
        self._record = record

        layout = QHBoxLayout()

        self._thumb = ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel(_TYPE_LABELS.get(record.prediction_type, "Predicted SMILES:")))
        self._result_field = QTextEdit(record.result_value() or "")
        self._result_field.setReadOnly(True)
        self._result_field.setPlaceholderText("Awaiting result…")
        self._result_field.setFixedHeight(64)
        self._result_field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        info.addWidget(self._result_field)

        info.addWidget(QLabel("Custom override:"))
        self._override_field = QLineEdit()
        self._override_field.setPlaceholderText("Leave blank to use the predicted value")
        info.addWidget(self._override_field)

        layout.addLayout(info)
        self.setLayout(layout)

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._thumb.update_record(record)
        self._result_field.setPlainText(record.result_value() or "")

    def apply_to_record(self) -> None:
        override = self._override_field.text().strip()
        self._record.approved_value = override if override else self._record.result_value()
        self._record.is_chemical = bool(self._record.approved_value)


class ReviewWindow(QWidget):
    def __init__(self, records: list[ImageRecord], config: Config, source_path: Path) -> None:
        super().__init__()
        self._records = records
        self._config = config
        self._source_path = source_path
        self._page = 0
        self._rows: list[_RecordRow] = []
        self._recognized = 0
        self._error_count = 0

        self.setWindowTitle(f"Review — {source_path.name}")
        self.setMinimumWidth(700)
        self._layout = QVBoxLayout()

        self._status_bar = QLabel(f"Identifying images…  (0 of {len(records)} done)")
        self._status_bar.setStyleSheet(
            "QLabel { background: #cce5ff; color: #004085; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._status_bar.setWordWrap(True)
        self._layout.addWidget(self._status_bar)

        self._grid = QVBoxLayout()
        self._layout.addLayout(self._grid)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("← Previous")
        self._prev_btn.clicked.connect(self._prev_page)
        self._page_label = QLabel()
        self._next_btn = QPushButton("Next →")
        self._next_btn.clicked.connect(self._next_page)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._page_label, alignment=Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._next_btn)
        self._layout.addLayout(nav)

        bottom = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.clicked.connect(self._accept)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(self._accept_btn)
        self._layout.addLayout(bottom)

        self.setLayout(self._layout)
        self._render_page()

    def _page_size(self) -> int:
        return self._config.page_size

    def _total_pages(self) -> int:
        return max(1, math.ceil(len(self._records) / self._page_size()))

    def _page_records(self) -> list[ImageRecord]:
        start = self._page * self._page_size()
        return self._records[start: start + self._page_size()]

    def _render_page(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = []
        for record in self._page_records():
            row = _RecordRow(record)
            self._rows.append(row)
            self._grid.addWidget(row)
        self._page_label.setText(f"Page {self._page + 1} of {self._total_pages()}")
        self._prev_btn.setEnabled(self._page > 0)
        is_last = self._page >= self._total_pages() - 1
        self._next_btn.setEnabled(not is_last)
        self._accept_btn.setText("Accept & Finish" if is_last else "Accept & Next →")

    def _prev_page(self):
        self._apply_current_page()
        self._page -= 1
        self._render_page()

    def _next_page(self):
        self._apply_current_page()
        self._page += 1
        self._render_page()

    def _apply_current_page(self):
        for row in self._rows:
            row.apply_to_record()

    def _accept(self):
        self._apply_current_page()
        is_last = self._page >= self._total_pages() - 1
        if not is_last:
            self._page += 1
            self._render_page()
            return
        try:
            out = write(self._records, self._source_path, self._config)
            msg = QMessageBox(self)
            msg.setWindowTitle("Done")
            msg.setText(f"Accessible file written to:\n{out}")
            msg.setIcon(QMessageBox.Icon.Information)
            open_btn = msg.addButton("Open File", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
            self.close()
        except Exception as exc:
            QMessageBox.critical(self, "Write Error", str(exc))

    def on_record_ready(self, record: ImageRecord) -> None:
        self._recognized += 1
        for row in self._rows:
            if row._record.id == record.id:
                row.update_record(record)
                break

    def on_recognition_status(self, msg: str) -> None:
        self._status_bar.setText(msg)

    def on_recognition_finished(self) -> None:
        total = len(self._records)
        if self._error_count:
            self._status_bar.setStyleSheet(
                "QLabel { background: #fff3cd; color: #856404; "
                "padding: 6px 10px; border-radius: 4px; }"
            )
            self._status_bar.setText(
                f"Identification complete — {total - self._error_count} of {total} succeeded. "
                f"{self._error_count} image(s) could not be identified. Review results below."
            )
        else:
            self._status_bar.setStyleSheet(
                "QLabel { background: #d4edda; color: #155724; "
                "padding: 6px 10px; border-radius: 4px; }"
            )
            self._status_bar.setText(
                f"Identification complete — {total} image(s) processed. Review results below."
            )

    def on_recognition_error(self, msg: str) -> None:
        self._error_count += 1
        self._status_bar.setStyleSheet(
            "QLabel { background: #fff3cd; color: #856404; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._status_bar.setText(f"Warning: {msg}")
```

- [ ] **Step 2: Delete `gui/namer_worker.py`**

```bash
rm gui/namer_worker.py
```

Verify no remaining imports:

```bash
grep -r "namer_worker" . --include="*.py"
```
Expected: no output

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add gui/review_window.py
git rm gui/namer_worker.py
git commit -m "feat: simplify ReviewWindow and remove namer_worker (pipeline handles name lookup)"
```
