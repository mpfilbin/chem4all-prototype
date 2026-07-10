# Decorative Image Prediction Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Decorative" prediction-type checkbox to the Select Images screen that, when checked, skips all model processing for that image and shows an editable "Decorative Image" placeholder in the Review screen.

**Architecture:** `"decorative"` becomes a valid value inside the existing `ImageRecord.prediction_types` list (no new field). The selection UI enforces it as mutually exclusive with the other four types. Because the worker's dispatch logic only acts on `{"smiles", "iupac", "trivial", "description"}`, a record whose only type is `"decorative"` already falls through every branch untouched — no worker or review-window code changes are needed, only tests proving that.

**Tech Stack:** Python, PyQt6, pytest.

## Global Constraints

- Follow existing code patterns in each file exactly (checkbox-per-type style, `QFrame` row style, existing test helper naming like `_make_record`).
- `prediction_types` default remains `["smiles"]` — unrelated to this feature, do not change.
- The decorative placeholder text is the exact literal string `"Decorative Image"` (spec-mandated), stored as a module-level constant in `models/image_record.py`, not duplicated elsewhere.
- Tests use `QT_QPA_PLATFORM=offscreen` (already set at the top of each GUI test file) — do not remove.
- Every new test must be run and confirmed passing before moving to the next task (TDD: write failing test, watch it fail, implement, watch it pass).

---

## Task 1: `ImageRecord.result_lines()` supports `"decorative"`

**Files:**
- Modify: `models/image_record.py:22-33`
- Test: `tests/test_image_record.py`

**Interfaces:**
- Produces: `ImageRecord.result_lines()` returns `["Decorative Image"]` whenever `"decorative"` is present in `self.prediction_types`, regardless of any other list contents.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_image_record.py` (after `test_result_lines_returns_multiple_types_in_fixed_order`):

```python
def test_result_lines_returns_decorative_placeholder():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        prediction_types=["decorative"],
    )
    assert record.result_lines() == ["Decorative Image"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_image_record.py::test_result_lines_returns_decorative_placeholder -v`
Expected: FAIL — `result_lines()` currently returns `[]` for an unrecognized type since `"decorative"` has no entry in `field_for_type`.

- [ ] **Step 3: Write minimal implementation**

In `models/image_record.py`, add a module-level constant next to `_TYPE_ORDER` and special-case it at the top of `result_lines()`:

```python
_TYPE_ORDER = ["smiles", "iupac", "trivial", "description"]
_DECORATIVE_TEXT = "Decorative Image"
```

```python
    def result_lines(self) -> list[str]:
        if "decorative" in self.prediction_types:
            return [_DECORATIVE_TEXT]
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_image_record.py -v`
Expected: all tests in the file PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "feat: support decorative prediction type in ImageRecord.result_lines"
```

---

## Task 2: Decorative checkbox in the Selection window

**Files:**
- Modify: `gui/selection_window.py:127-177` (the `_SelectionRow` class)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `ImageRecord` (unchanged), `Config`, `Path` — same as existing `SelectionWindow`/`_SelectionRow` constructors.
- Produces: `_SelectionRow._decorative_check` (`QCheckBox`), `_SelectionRow._other_checks` (`list[QCheckBox]`, the four existing type checkboxes in order `[smiles, iupac, trivial, describe]`), `_SelectionRow.prediction_types` returns `["decorative"]` when `_decorative_check` is checked (short-circuiting the other four). `connect_changed(slot)` also wires `_decorative_check.stateChanged`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_selection_window.py` (after `test_selection_row_reports_multiple_checked_types`):

```python
def test_decorative_checkbox_disables_other_prediction_checks():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]

    row._decorative_check.setChecked(True)

    assert row._smiles_check.isChecked() is False
    assert row._smiles_check.isEnabled() is False
    assert row._iupac_check.isEnabled() is False
    assert row._trivial_check.isEnabled() is False
    assert row._describe_check.isEnabled() is False
    assert row.prediction_types == ["decorative"]


def test_unchecking_decorative_restores_prior_checkbox_state():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row._iupac_check.setChecked(True)  # smiles True (default), iupac True

    row._decorative_check.setChecked(True)
    row._decorative_check.setChecked(False)

    assert row._smiles_check.isChecked() is True
    assert row._smiles_check.isEnabled() is True
    assert row._iupac_check.isChecked() is True
    assert row._trivial_check.isChecked() is False
    assert row._describe_check.isChecked() is False
    assert row.prediction_types == ["smiles", "iupac"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_selection_window.py::test_decorative_checkbox_disables_other_prediction_checks tests/test_selection_window.py::test_unchecking_decorative_restores_prior_checkbox_state -v`
Expected: FAIL — `_SelectionRow` has no `_decorative_check` attribute yet (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Replace the `_SelectionRow.__init__` body in `gui/selection_window.py` (from `self._smiles_check = QCheckBox("SMILES")` down through the end of `__init__`) so the full method reads:

```python
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

        self._decorative_check = QCheckBox("Decorative")
        layout.addWidget(self._decorative_check)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._smiles_check = QCheckBox("SMILES")
        self._iupac_check = QCheckBox("IUPAC Name")
        self._trivial_check = QCheckBox("Common Name")
        self._describe_check = QCheckBox("Describe Image")
        self._smiles_check.setChecked(True)
        self._other_checks = [
            self._smiles_check, self._iupac_check, self._trivial_check, self._describe_check,
        ]
        for box in self._other_checks:
            layout.addWidget(box)

        self._saved_other_states = [box.isChecked() for box in self._other_checks]
        self._decorative_check.stateChanged.connect(self._on_decorative_toggled)

    def _on_decorative_toggled(self) -> None:
        if self._decorative_check.isChecked():
            self._saved_other_states = [box.isChecked() for box in self._other_checks]
            for box in self._other_checks:
                box.setChecked(False)
                box.setEnabled(False)
        else:
            for box, was_checked in zip(self._other_checks, self._saved_other_states):
                box.setEnabled(True)
                box.setChecked(was_checked)

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
        self.checkbox.stateChanged.connect(slot)
        self._decorative_check.stateChanged.connect(slot)
        self._smiles_check.stateChanged.connect(slot)
        self._iupac_check.stateChanged.connect(slot)
        self._trivial_check.stateChanged.connect(slot)
        self._describe_check.stateChanged.connect(slot)
```

No new imports are needed — `QFrame` is already imported in `gui/selection_window.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_selection_window.py -v`
Expected: all tests in the file PASS, including the two new ones. (`test_selection_row_defaults_to_smiles_only` and `test_selection_row_reports_multiple_checked_types` must still pass unchanged — they don't touch `_decorative_check`.)

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "feat: add Decorative checkbox to selection row, mutually exclusive with other prediction types"
```

---

## Task 3: Validation treats Decorative as satisfying "at least one type"

**Files:**
- Modify: none (this task only adds a regression test for existing `SelectionWindow._update_identify_btn` logic, now exercised through the new checkbox from Task 2)
- Test: `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `SelectionWindow._identify_btn`, `SelectionWindow._error_banner`, `_SelectionRow._decorative_check` — all from Task 2 and pre-existing code.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_selection_window.py` (after `test_identify_button_disabled_when_included_row_has_no_types`):

```python
def test_identify_button_enabled_with_only_decorative_checked():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    window.show()
    row = window._rows[0]
    row._smiles_check.setChecked(False)
    assert window._identify_btn.isEnabled() is False  # sanity check: no types yet

    row._decorative_check.setChecked(True)

    assert window._identify_btn.isEnabled() is True
    assert window._error_banner.isVisible() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_selection_window.py::test_identify_button_enabled_with_only_decorative_checked -v`
Expected: FAIL at the sanity-check line only if Task 2 wasn't completed; if Task 2 is already merged, this should actually PASS immediately since `_update_identify_btn` already keys off `row.prediction_types`, which Task 2 made decorative-aware. Run it anyway to confirm — this step exists to lock in the behavior with a named regression test, not to drive new production code.

- [ ] **Step 3: (No implementation change expected)**

If Step 2 failed for a reason other than "Task 2 incomplete," stop and re-examine `SelectionWindow._update_identify_btn` in `gui/selection_window.py:86-101` — it should already read `row.prediction_types` generically with no changes needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_selection_window.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_selection_window.py
git commit -m "test: confirm decorative-only row satisfies selection validation"
```

---

## Task 4: Worker does no processing for decorative records

**Files:**
- Modify: none (`gui/worker.py` dispatch logic already excludes `"decorative"` from every branch)
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `RecognizerWorker` (unchanged), `ImageRecord(prediction_types=["decorative"])`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_worker.py` (after `test_worker_handles_multiple_prediction_types_in_one_record`):

```python
def test_worker_does_not_process_decorative_record(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("model call should not run for a decorative record")

    monkeypatch.setattr("gui.worker._run_decimer", _fail)
    monkeypatch.setattr("pipeline.describer.describe_image", _fail)

    record = _make_record(prediction_types=["decorative"])
    ready_records = []
    worker = RecognizerWorker([record], Config())
    worker.record_ready.connect(ready_records.append)
    worker.run()

    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.iupac_name is None
    assert record.trivial_name is None
    assert record.description is None
    assert len(ready_records) == 1
    assert ready_records[0] is record
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worker.py::test_worker_does_not_process_decorative_record -v`
Expected: PASS immediately — `gui/worker.py`'s dispatch (`types & {"smiles", "iupac", "trivial"}` and `"description" in types`) already excludes `"decorative"` from every branch, so no production code changes are needed. This step confirms that expectation in code; if it fails, inspect `gui/worker.py:31-85` for a branch that unexpectedly matches `"decorative"` (e.g. a wildcard/else clause) before making any change.

- [ ] **Step 3: (No implementation change expected)**

Only touch `gui/worker.py` if Step 2 surprises you. The design's premise is that no code change is needed here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_worker.py
git commit -m "test: confirm worker skips model calls for decorative records"
```

---

## Task 5: Review window renders and allows editing "Decorative Image"

**Files:**
- Modify: none (`gui/review_window.py` already composes text generically from `record.result_lines()`)
- Test: `tests/test_review_window.py`

**Interfaces:**
- Consumes: `_RecordRow(record, done)` (unchanged), `ImageRecord(prediction_types=["decorative"])`, `_RecordRow._restore_predicted()` (unchanged existing method).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_review_window.py` (after `test_record_row_editable_and_populated_when_done`):

```python
def test_record_row_shows_decorative_placeholder_when_done():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=True)
    assert row._value_field.isReadOnly() is False
    assert row._value_field.toPlainText() == "Decorative Image"


def test_restore_predicted_value_resets_decorative_text():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=True)
    row._value_field.setPlainText("edited alt text")

    row._restore_predicted()

    assert row._value_field.toPlainText() == "Decorative Image"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_window.py::test_record_row_shows_decorative_placeholder_when_done tests/test_review_window.py::test_restore_predicted_value_resets_decorative_text -v`
Expected: PASS immediately — `_RecordRow` already builds its text from `"\n\n".join(record.result_lines())`, and Task 1 made `result_lines()` decorative-aware. If either test fails, re-check `gui/review_window.py:40-44` (`_RecordRow.__init__`, the `done` branch) and `gui/review_window.py:76-78` (`_restore_predicted`) for a code path that bypasses `result_lines()`.

- [ ] **Step 3: (No implementation change expected)**

Only touch `gui/review_window.py` if Step 2 surprises you.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/test_review_window.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_review_window.py
git commit -m "test: confirm review window renders decorative placeholder as editable text"
```

---

## Task 6: Full regression pass

**Files:** none modified — verification only.

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest tests/ -v`
Expected: all tests PASS, including every test added in Tasks 1–5 and every pre-existing test (in particular `tests/test_image_record.py`, `tests/test_selection_window.py`, `tests/test_worker.py`, `tests/test_review_window.py`, `tests/test_writer.py`, `tests/test_reviewer.py`, `tests/test_pipeline_integration.py`).

- [ ] **Step 2: Manually smoke-test the checkbox layout (optional but recommended)**

Run the app (`python main.py` or the project's normal launch command), open a document with images via "Select Images," and visually confirm:
- The "Decorative" checkbox appears before the other four, separated by a vertical divider.
- Checking it unchecks and grays out the other four; unchecking it restores their prior state.
- Selecting only "Decorative" and proceeding to Review shows an editable "Decorative Image" text field for that image once processing completes (near-instant, since no model call runs).

- [ ] **Step 3: No commit needed for this task** (verification only; if manual testing surfaces a bug, open a new task to fix it with its own failing test first).
