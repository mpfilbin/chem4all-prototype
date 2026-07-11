# Toggle All Predictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 "Toggle All" buttons to the Select Images screen — one per prediction type (Decorative, SMILES, IUPAC, Common, Describe) — that check/uncheck that type across every row in one click, column-aligned above their respective checkboxes.

**Architecture:** `_SelectionRow` gains two public methods (`is_type_checked`, `set_type_checked`) that encapsulate the existing Decorative/other mutual-exclusion rule, plus `apply_column_widths` for layout. `SelectionWindow` gains a `_toggle_all_type` smart-toggle handler and a `_build_toggle_row` method that constructs a mirrored header row of buttons, using measured widths so checkbox columns widen to match their button labels.

**Tech Stack:** PyQt6, pytest (offscreen `QT_QPA_PLATFORM=offscreen`, no pytest-qt — direct widget construction/method calls per existing test style).

## Global Constraints

- Prediction type keys (must match existing `prediction_types` property values): `"decorative"`, `"smiles"`, `"iupac"`, `"trivial"`, `"description"`.
- Button labels (exact text, from spec): "Toggle All Decorative", "Toggle All SMILES", "Toggle All IUPAC", "Toggle All Common", "Toggle All Describe".
- Toggle semantics: if every row currently has the type checked, clicking unchecks all; otherwise clicking checks all.
- Checking a non-Decorative type across all rows must clear Decorative on any row that had it checked (reusing `_on_decorative_toggled`'s restore/re-enable behavior).
- No changes to `ImageRecord`, `ReviewWindow`, or any code outside `gui/selection_window.py` and its test file.

---

### Task 1: `_SelectionRow` type-checked accessor/mutator

**Files:**
- Modify: `gui/selection_window.py` (inside `_SelectionRow`, after the `prediction_types` property, before `connect_changed`)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Produces: `_SelectionRow._TYPE_ATTR: dict[str, str]`, `_SelectionRow.is_type_checked(pred_type: str) -> bool`, `_SelectionRow.set_type_checked(pred_type: str, checked: bool) -> None`. Later tasks call these instead of touching `_decorative_check`/`_smiles_check`/etc. directly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_selection_window.py` (anywhere after `_make_record`, e.g. right after `test_unchecking_decorative_restores_prior_checkbox_state`):

```python
def test_set_type_checked_decorative_sets_decorative_checkbox():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)

    row.set_type_checked("decorative", True)

    assert row._decorative_check.isChecked() is True
    assert row.is_type_checked("decorative") is True


def test_set_type_checked_non_decorative_clears_decorative_first():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    assert row._decorative_check.isChecked() is True  # default state

    row.set_type_checked("smiles", True)

    assert row._decorative_check.isChecked() is False
    assert row._smiles_check.isChecked() is True
    assert row.is_type_checked("smiles") is True


def test_set_type_checked_false_unchecks_without_touching_decorative():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._decorative_check.setChecked(False)
    row._smiles_check.setChecked(True)

    row.set_type_checked("smiles", False)

    assert row._smiles_check.isChecked() is False
    assert row._decorative_check.isChecked() is False
    assert row.is_type_checked("smiles") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection_window.py -k set_type_checked -v`
Expected: FAIL with `AttributeError: '_SelectionRow' object has no attribute 'set_type_checked'`

- [ ] **Step 3: Implement `is_type_checked` / `set_type_checked`**

In `gui/selection_window.py`, the `_SelectionRow` class currently ends with:

```python
    @property
    def prediction_types(self) -> list[str]:
        if self._decorative_check.isChecked():
            return ["decorative"]
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
```

Insert the new methods between `prediction_types` and `connect_changed`:

```python
    @property
    def prediction_types(self) -> list[str]:
        if self._decorative_check.isChecked():
            return ["decorative"]
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

    _TYPE_ATTR = {
        "decorative": "_decorative_check",
        "smiles": "_smiles_check",
        "iupac": "_iupac_check",
        "trivial": "_trivial_check",
        "description": "_describe_check",
    }

    def is_type_checked(self, pred_type: str) -> bool:
        return getattr(self, self._TYPE_ATTR[pred_type]).isChecked()

    def set_type_checked(self, pred_type: str, checked: bool) -> None:
        if pred_type == "decorative":
            self._decorative_check.setChecked(checked)
            return
        if checked and self._decorative_check.isChecked():
            self._decorative_check.setChecked(False)
        getattr(self, self._TYPE_ATTR[pred_type]).setChecked(checked)

    def connect_changed(self, slot) -> None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection_window.py -k set_type_checked -v`
Expected: 3 passed

- [ ] **Step 5: Run the full existing suite to check for regressions**

Run: `pytest tests/test_selection_window.py -v`
Expected: all pass (no changes to existing behavior)

- [ ] **Step 6: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "Add per-type checked accessor/mutator to _SelectionRow"
```

---

### Task 2: `SelectionWindow._toggle_all_type` smart-toggle handler

**Files:**
- Modify: `gui/selection_window.py` (inside `SelectionWindow`, immediately after `_set_all`)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `_SelectionRow.is_type_checked`, `_SelectionRow.set_type_checked` (Task 1).
- Produces: `SelectionWindow._toggle_all_type(pred_type: str) -> None`. Task 4 wires this to button clicks.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_selection_window.py`:

```python
def test_toggle_all_type_checks_all_rows_when_none_checked():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    for row in window._rows:
        row._decorative_check.setChecked(False)

    window._toggle_all_type("smiles")

    for row in window._rows:
        assert row.is_type_checked("smiles") is True
        assert row.is_type_checked("decorative") is False


def test_toggle_all_type_unchecks_all_rows_when_all_checked():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    for row in window._rows:
        row._decorative_check.setChecked(False)
        row._smiles_check.setChecked(True)

    window._toggle_all_type("smiles")

    for row in window._rows:
        assert row.is_type_checked("smiles") is False


def test_toggle_all_type_checks_all_rows_when_mixed():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    window._rows[0]._decorative_check.setChecked(False)
    window._rows[0]._smiles_check.setChecked(True)
    # window._rows[1] stays decorative-only (smiles unchecked) -> mixed state

    window._toggle_all_type("smiles")

    for row in window._rows:
        assert row.is_type_checked("smiles") is True
        assert row.is_type_checked("decorative") is False


def test_toggle_all_type_decorative_checks_all_rows_and_clears_others():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    for row in window._rows:
        row._decorative_check.setChecked(False)
        row._smiles_check.setChecked(True)

    window._toggle_all_type("decorative")

    for row in window._rows:
        assert row.is_type_checked("decorative") is True
        assert row._smiles_check.isChecked() is False
        assert row._smiles_check.isEnabled() is False


def test_toggle_all_type_noop_with_no_rows():
    window = SelectionWindow([], Config(), Path("dummy.pptx"))

    window._toggle_all_type("smiles")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection_window.py -k toggle_all_type -v`
Expected: FAIL with `AttributeError: 'SelectionWindow' object has no attribute '_toggle_all_type'`

- [ ] **Step 3: Implement `_toggle_all_type`**

In `gui/selection_window.py`, `SelectionWindow` currently has:

```python
    def _set_all(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)

    def _update_identify_btn(self) -> None:
```

Insert the new method between them:

```python
    def _set_all(self, checked: bool) -> None:
        for row in self._rows:
            row.checkbox.setChecked(checked)

    def _toggle_all_type(self, pred_type: str) -> None:
        if not self._rows:
            return
        all_checked = all(row.is_type_checked(pred_type) for row in self._rows)
        target = not all_checked
        for row in self._rows:
            row.set_type_checked(pred_type, target)

    def _update_identify_btn(self) -> None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection_window.py -k toggle_all_type -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "Add smart toggle-all-rows handler for prediction types"
```

---

### Task 3: `_SelectionRow.apply_column_widths`

**Files:**
- Modify: `gui/selection_window.py` (inside `_SelectionRow`, immediately after `set_type_checked` from Task 1)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `_SelectionRow._TYPE_ATTR` (Task 1).
- Produces: `_SelectionRow.apply_column_widths(widths: dict[str, int]) -> None`. Task 4 calls this once per row with computed column widths.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_selection_window.py`:

```python
def test_apply_column_widths_sets_fixed_checkbox_widths():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]

    row.apply_column_widths({"smiles": 150, "decorative": 120})

    assert row._smiles_check.minimumWidth() == 150
    assert row._smiles_check.maximumWidth() == 150
    assert row._decorative_check.minimumWidth() == 120
    assert row._decorative_check.maximumWidth() == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_selection_window.py -k apply_column_widths -v`
Expected: FAIL with `AttributeError: '_SelectionRow' object has no attribute 'apply_column_widths'`

- [ ] **Step 3: Implement `apply_column_widths`**

Directly after `set_type_checked` (added in Task 1):

```python
    def set_type_checked(self, pred_type: str, checked: bool) -> None:
        if pred_type == "decorative":
            self._decorative_check.setChecked(checked)
            return
        if checked and self._decorative_check.isChecked():
            self._decorative_check.setChecked(False)
        getattr(self, self._TYPE_ATTR[pred_type]).setChecked(checked)

    def apply_column_widths(self, widths: dict[str, int]) -> None:
        for pred_type, width in widths.items():
            getattr(self, self._TYPE_ATTR[pred_type]).setFixedWidth(width)

    def connect_changed(self, slot) -> None:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_selection_window.py -k apply_column_widths -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "Add per-row checkbox column-width control to _SelectionRow"
```

---

### Task 4: Wire the Toggle All button row into `SelectionWindow`

**Files:**
- Modify: `gui/selection_window.py` (`SelectionWindow.__init__`, plus a new `_build_toggle_row` method)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `SelectionWindow._toggle_all_type` (Task 2), `_SelectionRow.apply_column_widths` (Task 3).
- Produces: 5 `QPushButton`s (findable via `window.findChildren(QPushButton)` by their exact label text) wired to `_toggle_all_type`.

- [ ] **Step 1: Write the failing test**

Add to the top of `tests/test_selection_window.py`, update the PyQt6 import line:

```python
from PyQt6.QtWidgets import QApplication, QPushButton
```

Then add the test:

```python
def _find_button(window, text):
    return next(b for b in window.findChildren(QPushButton) if b.text() == text)


def test_toggle_all_smiles_button_checks_all_rows_and_clears_decorative():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )

    _find_button(window, "Toggle All SMILES").click()

    for row in window._rows:
        assert row.is_type_checked("smiles") is True
        assert row.is_type_checked("decorative") is False


def test_toggle_all_decorative_button_checks_all_rows():
    window = SelectionWindow(
        [_make_record("r1"), _make_record("r2")], Config(), Path("dummy.pptx")
    )
    for row in window._rows:
        row._decorative_check.setChecked(False)
        row._smiles_check.setChecked(True)

    _find_button(window, "Toggle All Decorative").click()

    for row in window._rows:
        assert row.is_type_checked("decorative") is True


def test_toggle_all_buttons_widen_checkbox_columns_to_match_button_width():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    button = _find_button(window, "Toggle All SMILES")

    # Compare minimumWidth (not .width()) since neither widget has been
    # shown/laid out yet — setFixedWidth guarantees minimumWidth immediately,
    # but actual geometry only updates on a layout pass.
    assert row._smiles_check.minimumWidth() == button.minimumWidth()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection_window.py -k toggle_all_smiles_button -v`
Expected: FAIL — `StopIteration` from `_find_button` (no such button exists yet)

- [ ] **Step 3: Implement `_build_toggle_row` and wire it into `__init__`**

In `gui/selection_window.py`, the current `SelectionWindow.__init__` body has this section:

```python
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
```

Replace it with:

```python
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
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        for record in records:
            row = _SelectionRow(record)
            row.connect_changed(self._update_identify_btn)
            self._rows.append(row)
            container_layout.addWidget(row)

        container_layout.addStretch()
        scroll.setWidget(container)

        layout.addLayout(self._build_toggle_row())
        layout.addWidget(scroll)
```

Then add the `_TOGGLE_BUTTONS`/`_DIVIDER_GAP` class attributes and `_build_toggle_row` method to `SelectionWindow`. Insert them immediately before `_set_all`:

```python
    _TOGGLE_BUTTONS = [
        ("decorative", "Toggle All Decorative", "Decorative"),
        ("smiles", "Toggle All SMILES", "SMILES"),
        ("iupac", "Toggle All IUPAC", "IUPAC Name"),
        ("trivial", "Toggle All Common", "Common Name"),
        ("description", "Toggle All Describe", "Describe Image"),
    ]
    _DIVIDER_GAP = 24  # tuned by eye in Task 5 to match the row's divider + spacing

    def _build_toggle_row(self) -> QHBoxLayout:
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(8, 0, 8, 0)

        include_spacer = QWidget()
        include_spacer.setFixedWidth(QCheckBox().sizeHint().width())
        toggle_row.addWidget(include_spacer)

        thumb_spacer = QWidget()
        thumb_spacer.setFixedWidth(72)
        toggle_row.addWidget(thumb_spacer)

        toggle_row.addStretch()

        widths: dict[str, int] = {}
        buttons: list[tuple[str, QPushButton]] = []
        for pred_type, button_text, checkbox_label in self._TOGGLE_BUTTONS:
            button = QPushButton(button_text)
            width = max(
                QCheckBox(checkbox_label).sizeHint().width(),
                button.sizeHint().width(),
            )
            button.setFixedWidth(width)
            widths[pred_type] = width
            buttons.append((pred_type, button))

        decorative_type, decorative_button = buttons[0]
        toggle_row.addWidget(decorative_button)
        toggle_row.addSpacing(self._DIVIDER_GAP)
        for pred_type, button in buttons[1:]:
            toggle_row.addWidget(button)

        for pred_type, button in buttons:
            button.clicked.connect(lambda _checked, t=pred_type: self._toggle_all_type(t))

        for row in self._rows:
            row.apply_column_widths(widths)

        return toggle_row

    def _set_all(self, checked: bool) -> None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection_window.py -v`
Expected: all pass, including the 3 new tests from Step 1

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "Wire Toggle All buttons into the Select Images header"
```

---

### Task 5: Visual alignment verification

**Files:**
- Modify (maybe): `gui/selection_window.py` (only the `_DIVIDER_GAP` constant, if misaligned)

No new interfaces — this task tunes the one magic constant from Task 4 by eye, using a real render instead of arithmetic.

- [ ] **Step 1: Render an offscreen screenshot**

Run this from the repo root (writes a PNG to the scratchpad, not the repo):

```bash
QT_QPA_PLATFORM=offscreen python3 -c "
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from config import Config
from models.image_record import ImageRecord
from gui.selection_window import SelectionWindow

app = QApplication(sys.argv)
records = [
    ImageRecord(id=f'r{i}', source_ref=f'slide {i}, shape 1', thumbnail_bytes=b'', recognition_bytes=b'')
    for i in range(6)
]
window = SelectionWindow(records, Config(), Path('dummy.pptx'))
window.resize(900, 500)
window.show()
app.processEvents()
window.grab().save('/private/tmp/claude-501/toggle_all_alignment.png')
"
```

(Adjust the save path to this session's actual scratchpad directory if different.)

- [ ] **Step 2: Read the screenshot**

Use the Read tool on the saved PNG. Check that each "Toggle All X" button sits horizontally centered above its column of checkboxes (Decorative, SMILES, IUPAC Name, Common Name, Describe Image) across all 6 rendered rows.

- [ ] **Step 3: Adjust `_DIVIDER_GAP` if misaligned**

If the SMILES/IUPAC/Common/Describe buttons are shifted left or right relative to their checkboxes (the Decorative button, sharing the leading spacers, should already line up), adjust the `_DIVIDER_GAP = 24` constant in `gui/selection_window.py` up or down and re-run Steps 1-2 until aligned. The leading columns (include-checkbox spacer, thumbnail spacer, stretch) don't need tuning since they use measured/fixed widths that already match the row exactly.

- [ ] **Step 4: Run the full test suite once more**

Run: `pytest tests/test_selection_window.py -v`
Expected: all pass (constant tuning doesn't change behavior, only a layout number)

- [ ] **Step 5: Commit if the constant changed**

```bash
git add gui/selection_window.py
git commit -m "Tune Toggle All button row divider-gap spacing"
```

If no change was needed, skip this commit.
