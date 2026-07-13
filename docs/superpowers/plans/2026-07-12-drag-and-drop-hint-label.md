# Drag-and-Drop Hint Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small, always-visible caption to `FilePickerWindow` telling the user they can drag and drop a file onto the window, not just use "Open File…".

**Architecture:** A single new `QLabel`, added as the last widget in `FilePickerWindow.__init__`'s `QVBoxLayout` (`gui/file_picker.py`), styled identically to the existing `_model_load_label` caption. No behavior changes — this is a static label with no show/hide logic.

**Tech Stack:** Python, PyQt6.

## Global Constraints

- Label text (verbatim): `"You can also drag and drop a file here to open it."`
- Label style (verbatim, matches `_model_load_label`): `"QLabel { color: #6c757d; font-size: 11px; }"`, center-aligned.
- The label is always visible — never `.hide()`/`.show()`'d based on extraction/download state.
- No other files or windows change.

Design spec: `docs/superpowers/specs/2026-07-12-drag-and-drop-hint-label-design.md`

---

### Task 1: Add drag-and-drop hint label to `FilePickerWindow`

**Files:**
- Modify: `gui/file_picker.py`
- Test: Modify `tests/test_file_picker.py`

**Interfaces:**
- Produces: `FilePickerWindow._drag_hint_label: QLabel` — a new instance attribute, always visible, with fixed text and stylesheet as specified in Global Constraints. No other code in this task consumes it; it's a leaf UI element.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_file_picker.py`:

```python
def test_drag_hint_label_visible_with_expected_text():
    window = FilePickerWindow(Config())
    assert window._drag_hint_label.text() == "You can also drag and drop a file here to open it."
    assert window._drag_hint_label.isVisible()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_file_picker.py -v -k drag_hint_label`
Expected: FAIL — `AttributeError: 'FilePickerWindow' object has no attribute '_drag_hint_label'`

- [ ] **Step 3: Add the label**

In `gui/file_picker.py`, in `FilePickerWindow.__init__`, immediately after the existing block that adds `self._extract_count_label` (currently the last widget added to `layout`, ending at `layout.addWidget(self._extract_count_label)`), add:

```python
        self._extract_count_label = QLabel()
        self._extract_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._extract_count_label.setStyleSheet("QLabel { color: #555; }")
        self._extract_count_label.hide()
        layout.addWidget(self._extract_count_label)

        self._drag_hint_label = QLabel("You can also drag and drop a file here to open it.")
        self._drag_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_hint_label.setStyleSheet("QLabel { color: #6c757d; font-size: 11px; }")
        layout.addWidget(self._drag_hint_label)

        self.setLayout(layout)
```

(Only the new `self._drag_hint_label = ...` through `layout.addWidget(self._drag_hint_label)` block is inserted — the `self.setLayout(layout)` line already exists immediately after `self._extract_count_label`'s block and is unchanged, just now follows the new label instead of preceding it.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_file_picker.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest -v`
Expected: PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add gui/file_picker.py tests/test_file_picker.py
git commit -m "Add drag-and-drop hint label to file picker window"
```

---

### Task 2: Manual verification

**Files:** none (manual QA only, no code changes)

- [ ] **Step 1: Launch the app**

Run the app per the project's normal launch method (see `gui/app.py` / `main.py`).

- [ ] **Step 2: Verify the label**

Confirm the new caption "You can also drag and drop a file here to open it." renders at the bottom of the window in the idle state, styled as a small muted-gray caption consistent with the rest of the window.

Trigger an extraction (open or drop a `.docx`/`.pptx`) and confirm the label remains visible below the status/progress UI while extraction is in progress, and after it completes.

- [ ] **Step 3: Report result**

No commit for this task — it's verification only. If an issue is found, fix it in Task 1 and re-commit there rather than adding a new task.
