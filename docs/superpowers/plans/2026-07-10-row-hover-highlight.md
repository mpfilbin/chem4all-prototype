# Row Hover Highlight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Highlight the row under the mouse cursor on both the Select Images screen and the Review screen with a subtle background tint.

**Architecture:** A single `HoverHighlightMixin` in `gui/widgets.py` implements the tint via `enterEvent`/`leaveEvent`, setting/clearing an imperative stylesheet. It's mixed into `_SelectionRow` (`gui/selection_window.py`) and `_RecordRow` (`gui/review_window.py`), the two per-image row widgets that back each screen's scrollable list.

**Tech Stack:** Python, PyQt6, pytest (offscreen `QApplication`, no `pytest-qt`).

## Global Constraints

- Hover tint color: `#eef3fb` (exact hex, both screens, no per-screen variation).
- No QSS `:hover` pseudo-class — behavior must be imperative (`enterEvent`/`leaveEvent` setting/clearing `styleSheet()`), per the design spec.
- No dark-mode variant, no theme system changes.
- No changes to selection/click behavior — visual only.
- Tests follow existing convention: instantiate widgets directly under an offscreen `QApplication`, no `qtbot`/`pytest-qt`.

Design spec: `docs/superpowers/specs/2026-07-10-row-hover-highlight-design.md`

---

### Task 1: `HoverHighlightMixin` in `gui/widgets.py`

**Files:**
- Modify: `gui/widgets.py`
- Test: Create `tests/test_widgets.py`

**Interfaces:**
- Produces: `HoverHighlightMixin` class in `gui/widgets.py`, with class attribute `HOVER_STYLESHEET: str = "background-color: #eef3fb;"` and methods `enterEvent(self, event) -> None` / `leaveEvent(self, event) -> None`. Any `QWidget` subclass that lists `HoverHighlightMixin` first in its bases (e.g. `class Foo(HoverHighlightMixin, QWidget)`) gets hover tinting for free — this is what Tasks 2 and 3 consume.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widgets.py`:

```python
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtWidgets import QApplication, QWidget

from gui.widgets import HoverHighlightMixin

_app = QApplication.instance() or QApplication(sys.argv)


class _HoverWidget(HoverHighlightMixin, QWidget):
    pass


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_enter_event_applies_hover_stylesheet():
    widget = _HoverWidget()
    assert widget.styleSheet() == ""

    widget.enterEvent(_enter_event())

    assert widget.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_leave_event_clears_hover_stylesheet():
    widget = _HoverWidget()
    widget.enterEvent(_enter_event())

    widget.leaveEvent(QEvent(QEvent.Type.Leave))

    assert widget.styleSheet() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_widgets.py -v`
Expected: FAIL — `ImportError: cannot import name 'HoverHighlightMixin' from 'gui.widgets'`

- [ ] **Step 3: Implement `HoverHighlightMixin`**

In `gui/widgets.py`, add the following class at the end of the file (after `ThumbnailLabel`):

```python
class HoverHighlightMixin:
    """Tints a widget's background while the mouse hovers over it."""

    HOVER_STYLESHEET = "background-color: #eef3fb;"

    def enterEvent(self, event) -> None:
        self.setStyleSheet(self.HOVER_STYLESHEET)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet("")
        super().leaveEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_widgets.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add gui/widgets.py tests/test_widgets.py
git commit -m "Add HoverHighlightMixin for row hover tinting"
```

---

### Task 2: Apply hover highlight to `_SelectionRow` (Select Images screen)

**Files:**
- Modify: `gui/selection_window.py:10` (import), `gui/selection_window.py:127` (class declaration)
- Test: Modify `tests/test_selection_window.py`

**Interfaces:**
- Consumes: `HoverHighlightMixin` from `gui/widgets.py` (Task 1) — mixed into `_SelectionRow`'s bases, no method calls needed at the call site.
- Produces: `_SelectionRow` instances now have a `styleSheet()` that changes on `enterEvent`/`leaveEvent`, verified via the existing `window._rows[0]` accessor pattern already used throughout this test file.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_selection_window.py`:

```python
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent

from gui.widgets import HoverHighlightMixin


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_selection_row_applies_hover_stylesheet_on_enter():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    assert row.styleSheet() == ""

    row.enterEvent(_enter_event())

    assert row.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_selection_row_clears_hover_stylesheet_on_leave():
    window = SelectionWindow([_make_record()], Config(), Path("dummy.pptx"))
    row = window._rows[0]
    row.enterEvent(_enter_event())

    row.leaveEvent(QEvent(QEvent.Type.Leave))

    assert row.styleSheet() == ""
```

Add the `from PyQt6.QtCore import QEvent, QPointF` / `from PyQt6.QtGui import QEnterEvent` / `from gui.widgets import HoverHighlightMixin` imports at the top of the file, alongside the existing imports (after the existing `from gui.selection_window import SelectionWindow` line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_selection_window.py -v -k hover`
Expected: FAIL — `AssertionError: assert '' == HoverHighlightMixin.HOVER_STYLESHEET` fails at the `enterEvent` assertion (row's `enterEvent` is still the base `QFrame` no-op, so `styleSheet()` stays `""`).

- [ ] **Step 3: Mix `HoverHighlightMixin` into `_SelectionRow`**

In `gui/selection_window.py`, change line 10:

```python
from gui.widgets import ThumbnailLabel
```

to:

```python
from gui.widgets import ThumbnailLabel, HoverHighlightMixin
```

Then change line 127:

```python
class _SelectionRow(QFrame):
```

to:

```python
class _SelectionRow(HoverHighlightMixin, QFrame):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_selection_window.py -v`
Expected: PASS (all tests, including the 2 new hover tests)

- [ ] **Step 5: Commit**

```bash
git add gui/selection_window.py tests/test_selection_window.py
git commit -m "Highlight selection rows on hover"
```

---

### Task 3: Apply hover highlight to `_RecordRow` (Review screen)

**Files:**
- Modify: `gui/review_window.py:14` (import), `gui/review_window.py:17-19` (class declaration + `__init__`)
- Test: Modify `tests/test_review_window.py`

**Interfaces:**
- Consumes: `HoverHighlightMixin` from `gui/widgets.py` (Task 1) — mixed into `_RecordRow`'s bases.
- Produces: `_RecordRow` instances now have a `styleSheet()` that changes on `enterEvent`/`leaveEvent`, verified via direct `_RecordRow(record, done=...)` construction, matching this file's existing pattern.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_review_window.py`:

```python
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QEnterEvent

from gui.widgets import HoverHighlightMixin


def _enter_event() -> QEnterEvent:
    return QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))


def test_record_row_applies_hover_stylesheet_on_enter():
    row = _RecordRow(_make_record(), done=False)
    assert row.styleSheet() == ""

    row.enterEvent(_enter_event())

    assert row.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET


def test_record_row_clears_hover_stylesheet_on_leave():
    row = _RecordRow(_make_record(), done=False)
    row.enterEvent(_enter_event())

    row.leaveEvent(QEvent(QEvent.Type.Leave))

    assert row.styleSheet() == ""
```

Add the `from PyQt6.QtCore import QEvent, QPointF` / `from PyQt6.QtGui import QEnterEvent` / `from gui.widgets import HoverHighlightMixin` imports at the top of the file, alongside the existing imports (after the existing `from gui.review_window import ReviewWindow, _RecordRow` line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_review_window.py -v -k hover`
Expected: FAIL — `AssertionError: assert '' == HoverHighlightMixin.HOVER_STYLESHEET` (row's `enterEvent` is still the base `QWidget` no-op).

- [ ] **Step 3: Mix `HoverHighlightMixin` into `_RecordRow` and enable styled backgrounds**

In `gui/review_window.py`, change line 14:

```python
from gui.widgets import ThumbnailLabel
```

to:

```python
from gui.widgets import ThumbnailLabel, HoverHighlightMixin
```

Then change lines 17-19:

```python
class _RecordRow(QWidget):
    def __init__(self, record: ImageRecord, done: bool, parent=None):
        super().__init__(parent)
```

to:

```python
class _RecordRow(HoverHighlightMixin, QWidget):
    def __init__(self, record: ImageRecord, done: bool, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
```

(`Qt` is already imported at the top of `gui/review_window.py` via `from PyQt6.QtCore import Qt, QUrl`, so no new import is needed for this attribute. `WA_StyledBackground` is required because, unlike `QFrame`, a plain `QWidget` does not paint a stylesheet `background-color` by default.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_review_window.py -v`
Expected: PASS (all tests, including the 2 new hover tests)

- [ ] **Step 5: Commit**

```bash
git add gui/review_window.py tests/test_review_window.py
git commit -m "Highlight review rows on hover"
```

---

### Task 4: Manual verification

**Files:** none (manual QA only, no code changes)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests, no regressions)

- [ ] **Step 2: Launch the app and visually verify both screens**

Run the app per the project's normal launch method (see `gui/app.py`), open a file that produces multiple image rows, and:
- On the Select Images screen, move the mouse over each row and confirm the row background tints to `#eef3fb` and clears on mouse-out, without affecting checkbox/thumbnail behavior.
- Proceed to the Review screen (or open it directly if possible) and repeat the same hover check on its rows, confirming the `QTextEdit` keeps its own white background while the surrounding row tints.

- [ ] **Step 3: Report result**

No commit for this task — it's verification only. If a visual issue is found, fix it in the relevant task above and re-commit there rather than adding a new task.
