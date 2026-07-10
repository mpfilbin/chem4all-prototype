# Editable Predicted Value Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the read-only "Predicted SMILES" box and the "Custom override" box on the Review screen into a single editable, scrollable field whose edits persist across Previous/Next navigation, survive async prediction updates safely, and can be undone via a Restore button — plus a hint banner explaining the new behavior.

**Architecture:** All changes live in `gui/review_window.py`. `_RecordRow` gets its two text widgets collapsed into one editable `QTextEdit` with a dirty-tracking flag and a conditional restore button; `ReviewWindow` gains one static hint label above the scroll area.

**Tech Stack:** PyQt6 (`QTextEdit`, `QPushButton`, `QLabel`), no new dependencies.

## Global Constraints

- No changes to `models/image_record.py` — `ImageRecord.approved_value` / `is_chemical` remain the only fields written.
- No new automated GUI tests are added — `pytest-qt` is not a project dependency and `gui/review_window.py` has no existing widget tests; verification is manual (per `docs/superpowers/specs/2026-07-09-editable-predicted-value-design.md`).
- An emptied field means "not a chemical" / excluded from output (this is a deliberate change from the old behavior where a blank override fell back to the prediction).

---

### Task 1: Merge predicted-value and override fields in `_RecordRow`

**Files:**
- Modify: `gui/review_window.py:1-60` (imports and `_RecordRow` class)

**Interfaces:**
- Consumes: `ImageRecord.result_value()`, `ImageRecord.approved_value`, `ImageRecord.is_chemical` (all existing, from `models/image_record.py`).
- Produces: `_RecordRow.__init__(record, parent=None)`, `_RecordRow.update_record(record)`, `_RecordRow.apply_to_record()` — same signatures as before, so `ReviewWindow` (Task 2 and existing code) needs no interface changes.

- [ ] **Step 1: Replace the `_RecordRow` class**

Edit `gui/review_window.py`. First, drop the now-unused `QLineEdit` import on line 8:

```python
# Before
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit,
    QMessageBox, QScrollArea,
)

# After
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit,
    QMessageBox, QScrollArea,
)
```

Then replace the entire `_RecordRow` class (currently lines 23-60) with:

```python
class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, parent=None):
        super().__init__(parent)
        self._record = record
        self._edited = False

        layout = QHBoxLayout()

        self._thumb = ThumbnailLabel(record)
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel(_TYPE_LABELS.get(record.prediction_type, "Predicted SMILES:")))
        initial_text = (
            record.approved_value
            if record.approved_value is not None
            else (record.result_value() or "")
        )
        self._value_field = QTextEdit(initial_text)
        self._value_field.setPlaceholderText("Awaiting result…")
        self._value_field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        metrics = self._value_field.fontMetrics()
        frame = self._value_field.frameWidth() * 2
        self._value_field.setFixedHeight(metrics.lineSpacing() * 4 + frame + 12)
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
        predicted = self._record.result_value() or ""
        self._restore_btn.setVisible(self._value_field.toPlainText() != predicted)

    def _restore_predicted(self) -> None:
        self._set_field_text(self._record.result_value() or "")
        self._edited = False

    def update_record(self, record: ImageRecord) -> None:
        self._record = record
        self._thumb.update_record(record)
        if not self._edited:
            self._set_field_text(record.result_value() or "")

    def apply_to_record(self) -> None:
        value = self._value_field.toPlainText().strip()
        self._record.approved_value = value
        self._record.is_chemical = bool(value)
```

- [ ] **Step 2: Manual verification — sizing, editing, and blank-excludes behavior**

Create a throwaway harness script at `/tmp/verify_record_row.py`:

```python
import sys
from PyQt6.QtWidgets import QApplication
from gui.review_window import _RecordRow
from models.image_record import ImageRecord

app = QApplication(sys.argv)
record = ImageRecord(
    id="1", source_ref="test slide 1",
    thumbnail_bytes=b"", recognition_bytes=b"",
    predicted_smiles="CCO." * 30,
    prediction_type="smiles",
)
row = _RecordRow(record)
row.resize(500, 300)
row.show()
app.exec()
row.apply_to_record()
print("approved_value:", repr(record.approved_value))
print("is_chemical:", record.is_chemical)
```

Run: `python /tmp/verify_record_row.py`

Confirm, before closing the window:
- The predicted value box shows ~4 lines of the long SMILES string and scrolls internally instead of growing — the "↺ Restore predicted value" button is **not** visible (text matches the prediction).
- Typing in the box is possible (it's no longer read-only), and there's no separate "Custom override" field or label.
- After typing any character, the Restore button appears.
- Clear the box entirely — the Restore button is still visible (text differs from prediction, which is non-empty).
- Click Restore — the original `CCO.` string comes back and the Restore button disappears.

Close the window, then check the printed output: `approved_value` should equal the final field text (stripped) and `is_chemical` should be `True` (since the field was restored to a non-empty value). Re-run the script, clear the field, and close without clicking Restore — this time confirm the printed `approved_value` is `''` and `is_chemical` is `False`.

Delete the harness script when done: `rm /tmp/verify_record_row.py`.

- [ ] **Step 3: Manual verification — late async prediction does not clobber an in-progress edit**

Create a second throwaway harness script at `/tmp/verify_race_condition.py`:

```python
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from gui.review_window import _RecordRow
from models.image_record import ImageRecord

app = QApplication(sys.argv)
record = ImageRecord(
    id="1", source_ref="test slide 1",
    thumbnail_bytes=b"", recognition_bytes=b"",
    predicted_smiles="INITIAL", prediction_type="smiles",
)
row = _RecordRow(record)
row.resize(500, 300)
row.show()


def simulate_late_prediction():
    late_record = ImageRecord(
        id="1", source_ref="test slide 1",
        thumbnail_bytes=b"", recognition_bytes=b"",
        predicted_smiles="LATE-PREDICTION-SHOULD-NOT-APPEAR",
        prediction_type="smiles",
    )
    row.update_record(late_record)
    print("late prediction delivered; field now shows:", repr(row._value_field.toPlainText()))


QTimer.singleShot(4000, simulate_late_prediction)
app.exec()
```

Run: `python /tmp/verify_race_condition.py`, and **within the first 4 seconds**, click into the field and replace its text with `MY-EDIT`. After ~4 seconds the simulated late prediction fires (printed to the terminal).

Confirm the field still shows `MY-EDIT`, not `LATE-PREDICTION-SHOULD-NOT-APPEAR` — this proves the `_edited` dirty flag protects an in-progress edit from being overwritten. Close the window.

Now run it a second time (`python /tmp/verify_race_condition.py`) and this time **do not type anything** before the timer fires. Confirm the field updates to `LATE-PREDICTION-SHOULD-NOT-APPEAR` once the terminal prints the "late prediction delivered" line — this proves unedited rows still pick up predictions normally.

Delete the harness script when done: `rm /tmp/verify_race_condition.py`.

- [ ] **Step 4: Commit**

```bash
git add gui/review_window.py
git commit -m "$(cat <<'EOF'
feat: merge predicted-value and override fields into one editable box

Combines the read-only prediction display and the separate override
line-edit into a single scrollable, editable QTextEdit per record row,
with a dirty flag so late-arriving async predictions never clobber an
in-progress edit, and a Restore button to undo an accidental clear.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Persist edits across Previous/Next navigation

**Files:**
- Modify: `gui/review_window.py` (no code change expected — this task verifies existing navigation plumbing works correctly with the new field)

**Interfaces:**
- Consumes: `_RecordRow.apply_to_record()` and `_RecordRow.__init__` pre-fill logic from Task 1; `ReviewWindow._apply_current_page()`, `_prev_page()`, `_next_page()`, `_render_page()` (all pre-existing, unchanged).

`ReviewWindow._prev_page` and `_next_page` already call `_apply_current_page()` (which calls `apply_to_record()` on every visible row) before swapping `self._page` and calling `_render_page()`, which rebuilds `_RecordRow` instances from `self._records`. Task 1's `__init__` pre-fill (`record.approved_value if record.approved_value is not None else ...`) is what makes an edit reappear when the user navigates back. No production code changes are needed here — this task is a manual end-to-end check that the wiring actually behaves as designed with real page transitions (Task 1's harness only exercised a single row in isolation).

- [ ] **Step 1: Manual verification — edit survives Previous/Next**

Create a throwaway harness script at `/tmp/verify_review_window.py`:

```python
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from config import Config
from gui.review_window import ReviewWindow
from models.image_record import ImageRecord

app = QApplication(sys.argv)
records = [
    ImageRecord(
        id=str(i), source_ref=f"slide {i}",
        thumbnail_bytes=b"", recognition_bytes=b"",
        predicted_smiles=f"C{'C' * i}O", prediction_type="smiles",
    )
    for i in range(1, 4)
]
config = Config(page_size=1)
window = ReviewWindow(records, config, Path("/tmp/does-not-matter.pptx"))
window.on_recognition_finished()
window.show()
app.exec()
for r in records:
    print(r.id, repr(r.approved_value), r.is_chemical)
```

Run: `python /tmp/verify_review_window.py`

With `page_size=1`, each page shows exactly one record. In the window:
1. On page 1, edit the value field to `EDITED-ONE`, then click "Next →".
2. On page 2, leave the field untouched, click "Next →".
3. On page 3, clear the field entirely (leave blank), then click "← Previous" twice to get back to page 1.
4. Confirm page 1 still shows `EDITED-ONE` in the field (the edit persisted across two round trips) and its Restore button is visible (differs from the original prediction).
5. Navigate forward to page 3 again and confirm it's still blank, with the Restore button visible there too.
6. Close the window.

Check the printed output: record `1`'s `approved_value` should be `'EDITED-ONE'` with `is_chemical=True`; record `2`'s `approved_value` should equal its original predicted SMILES (`'CCO'`) with `is_chemical=True` (never edited, so `apply_to_record` just re-applies the unedited prediction text); record `3`'s `approved_value` should be `''` with `is_chemical=False`.

Delete the harness script when done: `rm /tmp/verify_review_window.py`.

- [ ] **Step 2: Commit**

No production files changed in this task — nothing to commit. If verification reveals a bug, fix it in `gui/review_window.py`, re-run Step 1, then commit that fix:

```bash
git add gui/review_window.py
git commit -m "$(cat <<'EOF'
fix: correct edit persistence across Review screen page navigation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add the editable-field hint banner to `ReviewWindow`

**Files:**
- Modify: `gui/review_window.py:63-95` (`ReviewWindow.__init__`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ReviewWindow._hint_banner` (a `QLabel`), purely additive — no other code depends on it.

- [ ] **Step 1: Add the hint banner widget**

In `gui/review_window.py`, inside `ReviewWindow.__init__`, immediately after the existing `self._layout.addWidget(self._status_bar)` line (around line 85) and before the `self._scroll_area = QScrollArea()` line, insert:

```python
        self._hint_banner = QLabel(
            "Predicted values are editable — edit a field to override the "
            "prediction in the exported file. Clearing a field excludes "
            "that image; use Restore to undo."
        )
        self._hint_banner.setWordWrap(True)
        self._hint_banner.setStyleSheet(
            "QLabel { background: #f0f0f0; color: #444; "
            "padding: 6px 10px; border-radius: 4px; }"
        )
        self._layout.addWidget(self._hint_banner)
```

- [ ] **Step 2: Manual verification — banner is visible and reads correctly**

Reuse the harness from Task 2 (`/tmp/verify_review_window.py`, recreate it if deleted) and run it again:

```bash
python /tmp/verify_review_window.py
```

Confirm the gray hint banner appears above the record list, below the blue "Identifying images…" status bar, and its text is fully readable (wraps rather than clipping) at the window's default width. Close the window and delete the harness script: `rm /tmp/verify_review_window.py`.

- [ ] **Step 3: Commit**

```bash
git add gui/review_window.py
git commit -m "$(cat <<'EOF'
feat: add hint banner explaining editable predicted-value field

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
