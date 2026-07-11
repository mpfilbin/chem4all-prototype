# Review Prediction Pills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the Review screen, show a colored "pill" for each prediction type (SMILES, IUPAC, Trivial, Description, Decorative) that was requested for that image, floating to the right of the "Prediction Results:" label.

**Architecture:** Module-level constants in `gui/review_window.py` define pill order, labels, and colors. A `_make_pill(pred_type)` helper builds a styled `QLabel` per type. `_RecordRow.__init__` replaces its standalone "Prediction Results:" label with a `QHBoxLayout` containing the label, a stretch, and one pill per requested type (in fixed order).

**Tech Stack:** Python, PyQt6, pytest (offscreen `QApplication`, no `pytest-qt`).

## Global Constraints

- Pill order: `["decorative", "smiles", "iupac", "trivial", "description"]` — always in this order regardless of the order types appear in `ImageRecord.prediction_types`.
- Pill labels: `"Decorative"`, `"SMILES"`, `"IUPAC"`, `"Trivial"`, `"Description"` (short forms).
- Pill colors (fixed, not theme-derived; white text on all): Decorative `#6c757d`, SMILES `#0d6efd`, IUPAC `#6f42c1`, Trivial `#198754`, Description `#fd7e14`.
- Pills are static — no tooltip, no click behavior, no legend.
- `"decorative"` is mutually exclusive with the other four types (enforced upstream in `SelectionWindow`), so it only ever renders as a lone pill.
- Pills are built once at `_RecordRow` construction; `update_record()` needs no pill-related changes since `prediction_types` never changes after `ReviewWindow` is constructed.
- Tests follow existing convention: instantiate widgets directly under an offscreen `QApplication`, no `qtbot`/`pytest-qt`.

Design spec: `docs/superpowers/specs/2026-07-11-review-prediction-pills-design.md`

---

### Task 1: Pill constants and `_make_pill` helper in `gui/review_window.py`

**Files:**
- Modify: `gui/review_window.py` (add module-level constants and helper function, near the top of the file after imports, before `_RecordRow`)
- Test: Modify `tests/test_review_window.py`

**Interfaces:**
- Produces: module-level constants `_PILL_ORDER: list[str]`, `_PILL_LABELS: dict[str, str]`, `_PILL_COLORS: dict[str, str]`, and function `_make_pill(pred_type: str) -> QLabel` in `gui/review_window.py`. Task 2 consumes all four to build the header row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_review_window.py`:

```python
from gui.review_window import _make_pill, _PILL_COLORS, _PILL_LABELS


def test_make_pill_sets_label_text():
    pill = _make_pill("smiles")
    assert pill.text() == "SMILES"


def test_make_pill_sets_background_color():
    pill = _make_pill("iupac")
    assert _PILL_COLORS["iupac"] in pill.styleSheet()


def test_make_pill_labels_cover_all_prediction_types():
    for pred_type in ["decorative", "smiles", "iupac", "trivial", "description"]:
        pill = _make_pill(pred_type)
        assert pill.text() == _PILL_LABELS[pred_type]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review_window.py -v -k make_pill`
Expected: FAIL — `ImportError: cannot import name '_make_pill' from 'gui.review_window'`

- [ ] **Step 3: Implement the constants and helper**

In `gui/review_window.py`, add after the existing imports (after the `from gui.widgets import ThumbnailLabel, HoverHighlightMixin` line) and before `class _RecordRow(HoverHighlightMixin, QWidget):`:

```python
_PILL_ORDER = ["decorative", "smiles", "iupac", "trivial", "description"]
_PILL_LABELS = {
    "decorative": "Decorative", "smiles": "SMILES", "iupac": "IUPAC",
    "trivial": "Trivial", "description": "Description",
}
_PILL_COLORS = {
    "decorative": "#6c757d", "smiles": "#0d6efd", "iupac": "#6f42c1",
    "trivial": "#198754", "description": "#fd7e14",
}


def _make_pill(pred_type: str) -> QLabel:
    pill = QLabel(_PILL_LABELS[pred_type])
    pill.setStyleSheet(
        f"background-color: {_PILL_COLORS[pred_type]}; color: white; "
        "border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
    )
    return pill
```

`QLabel` is already imported at the top of `gui/review_window.py` via the existing `from PyQt6.QtWidgets import (...)` block, so no new import is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review_window.py -v -k make_pill`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/review_window.py tests/test_review_window.py
git commit -m "Add prediction-type pill constants and builder"
```

---

### Task 2: Wire pills into `_RecordRow`'s header row

**Files:**
- Modify: `gui/review_window.py:30-33` (the `info` layout construction in `_RecordRow.__init__`)
- Test: Modify `tests/test_review_window.py`

**Interfaces:**
- Consumes: `_PILL_ORDER`, `_make_pill` from `gui/review_window.py` (Task 1).
- Produces: `_RecordRow` instances whose `info` layout's first item is a `QHBoxLayout` (accessible via `info.itemAt(0).layout()`) containing the "Prediction Results:" label followed by one `QLabel` pill per requested prediction type, in `_PILL_ORDER` order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_review_window.py`:

```python
from PyQt6.QtWidgets import QLabel


def _header_pill_texts(row: _RecordRow) -> list[str]:
    info = row.layout().itemAt(1).layout()  # info QVBoxLayout is item 1 of the row's QHBoxLayout
    header_row = info.itemAt(1).layout()  # header_row QHBoxLayout is item 1 of info (item 0 is source_ref label)
    texts = []
    for i in range(header_row.count()):
        item = header_row.itemAt(i)
        widget = item.widget()
        if isinstance(widget, QLabel) and widget.text() != "Prediction Results:":
            texts.append(widget.text())
    return texts


def test_record_row_shows_pills_in_fixed_order():
    record = _make_record(prediction_types=["description", "smiles"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["SMILES", "Description"]


def test_record_row_shows_single_decorative_pill():
    record = _make_record(prediction_types=["decorative"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["Decorative"]


def test_record_row_shows_all_four_non_decorative_pills():
    record = _make_record(prediction_types=["trivial", "iupac", "description", "smiles"])
    row = _RecordRow(record, done=False)
    assert _header_pill_texts(row) == ["SMILES", "IUPAC", "Trivial", "Description"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review_window.py -v -k shows_pills or shows_single_decorative or shows_all_four`
Expected: FAIL — `AssertionError` (header row currently contains no pills, only the "Prediction Results:" label with no layout wrapper, so `_header_pill_texts` returns `[]` or raises `AttributeError` since `info.itemAt(0)` is a widget item, not a layout item)

- [ ] **Step 3: Replace the standalone label with a header row containing pills**

In `gui/review_window.py`, change:

```python
        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        info.addWidget(QLabel("Prediction Results:"))
```

to:

```python
        info = QVBoxLayout()
        info.addWidget(QLabel(record.source_ref))

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Prediction Results:"))
        header_row.addStretch()
        for pred_type in _PILL_ORDER:
            if pred_type in record.prediction_types:
                header_row.addWidget(_make_pill(pred_type))
        info.addLayout(header_row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review_window.py -v`
Expected: PASS (all tests, including the 3 new pill-order tests, with no regressions in the existing suite)

- [ ] **Step 5: Commit**

```bash
git add gui/review_window.py tests/test_review_window.py
git commit -m "Show prediction-type pills on Review screen rows"
```

---

### Task 3: Manual verification

**Files:** none (manual QA only, no code changes)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests, no regressions)

- [ ] **Step 2: Launch the app and visually verify the Review screen**

Run the app per the project's normal launch method (see `gui/app.py`), select a file, choose a mix of prediction types across a few images on the Select Images screen (e.g. one image with SMILES + IUPAC, one with all four, one Decorative), and proceed to the Review screen. Confirm:
- Each row shows pills to the right of "Prediction Results:", not wrapping awkwardly or overlapping the text box below.
- Pill colors match the spec (SMILES blue, IUPAC purple, Trivial green, Description orange, Decorative gray) and are legible (white text) in both light and dark system appearance.
- Pill order is consistent across rows regardless of which types were selected first.

- [ ] **Step 3: Report result**

No commit for this task — it's verification only. If a visual issue is found, fix it in Task 2 and re-commit there rather than adding a new task.
