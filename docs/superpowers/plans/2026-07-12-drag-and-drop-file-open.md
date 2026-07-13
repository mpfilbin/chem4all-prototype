# Drag-and-Drop File Open Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user drag a single `.docx`/`.pptx` file onto the `FilePickerWindow` to open and extract it, in addition to the existing "Open File…" button.

**Architecture:** `FilePickerWindow` (`gui/file_picker.py`) opts into Qt drag-and-drop via `setAcceptDrops(True)` and overrides `dragEnterEvent`/`dragLeaveEvent`/`dropEvent`. A shared `_is_valid_drag` helper enforces the accept rule (single local file, `.docx`/`.pptx` extension, window not busy) and is reused by both `dragEnterEvent` (to decide whether to accept + highlight) and `dropEvent` (to decide whether to actually extract). A valid drop calls the existing `_start_extraction(path)` — the same method the button already calls — so extraction/progress/error handling need no changes.

**Tech Stack:** Python, PyQt6, pytest (offscreen `QApplication`, no `pytest-qt`).

## Global Constraints

- Only `.docx` and `.pptx` (case-insensitive) single-file drops are accepted; anything else (wrong extension, multiple files, non-local URLs) is silently ignored (standard Qt "not allowed" cursor) — no dialog.
- Drops are rejected whenever `self._open_btn.isEnabled()` is `False` (model download or extraction in progress) — reuses that existing flag rather than introducing a new busy-state variable.
- Drag-and-drop applies only to `FilePickerWindow` — no changes to `SelectionWindow`, `ReviewWindow`, or `SettingsDialog`.
- Drag highlight is a dashed `2px` border, color `#0d6efd`, applied via `self.setStyleSheet(...)` and cleared to `""` on drag-leave/drop — same imperative-stylesheet pattern as `HoverHighlightMixin` in `gui/widgets.py`.
- Tests follow existing convention: instantiate widgets directly under an offscreen `QApplication`, no `qtbot`/`pytest-qt`.

Design spec: `docs/superpowers/specs/2026-07-12-drag-and-drop-file-open-design.md`

---

### Task 1: Drag-and-drop support on `FilePickerWindow`

**Files:**
- Modify: `gui/file_picker.py`
- Test: Create `tests/test_file_picker.py`

**Interfaces:**
- Produces: `FilePickerWindow._DRAG_HIGHLIGHT_STYLESHEET: str` (class attribute), `FilePickerWindow._is_valid_drag(self, event) -> bool`, and overridden `dragEnterEvent`/`dragLeaveEvent`/`dropEvent` methods. A valid drop calls `self._start_extraction(path: Path)` — the pre-existing method used by the "Open File…" button (`gui/file_picker.py:211`), unchanged by this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_file_picker.py`:

```python
from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from unittest.mock import MagicMock

from PyQt6.QtCore import QPoint, QPointF, Qt, QMimeData, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import QApplication

from config import Config
from gui.file_picker import FilePickerWindow

_app = QApplication.instance() or QApplication(sys.argv)


def _drag_enter_event(paths: list[str]) -> QDragEnterEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return QDragEnterEvent(
        QPoint(0, 0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def _drop_event(paths: list[str]) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return QDropEvent(
        QPointF(0, 0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def test_is_valid_drag_accepts_single_docx():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.docx"])) is True


def test_is_valid_drag_accepts_single_pptx():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.pptx"])) is True


def test_is_valid_drag_rejects_wrong_extension():
    window = FilePickerWindow(Config())
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.pdf"])) is False


def test_is_valid_drag_rejects_multiple_files():
    window = FilePickerWindow(Config())
    event = _drag_enter_event(["/tmp/a.docx", "/tmp/b.docx"])
    assert window._is_valid_drag(event) is False


def test_is_valid_drag_rejects_when_open_button_disabled():
    window = FilePickerWindow(Config())
    window._open_btn.setEnabled(False)
    assert window._is_valid_drag(_drag_enter_event(["/tmp/sample.docx"])) is False


def test_drag_enter_event_highlights_window_for_valid_drag():
    window = FilePickerWindow(Config())
    assert window.styleSheet() == ""

    event = _drag_enter_event(["/tmp/sample.docx"])
    window.dragEnterEvent(event)

    assert window.styleSheet() == FilePickerWindow._DRAG_HIGHLIGHT_STYLESHEET
    assert event.isAccepted()


def test_drag_enter_event_ignores_invalid_drag():
    window = FilePickerWindow(Config())

    event = _drag_enter_event(["/tmp/sample.pdf"])
    window.dragEnterEvent(event)

    assert window.styleSheet() == ""
    assert not event.isAccepted()


def test_drag_leave_event_clears_highlight():
    window = FilePickerWindow(Config())
    window.dragEnterEvent(_drag_enter_event(["/tmp/sample.docx"]))

    window.dragLeaveEvent(QDragLeaveEvent())

    assert window.styleSheet() == ""


def test_drop_event_starts_extraction_with_dropped_path(tmp_path):
    window = FilePickerWindow(Config())
    window._start_extraction = MagicMock()
    docx_path = tmp_path / "dropped.docx"
    docx_path.write_bytes(b"")

    window.dropEvent(_drop_event([str(docx_path)]))

    window._start_extraction.assert_called_once_with(docx_path)
    assert window.styleSheet() == ""


def test_drop_event_ignores_invalid_drop():
    window = FilePickerWindow(Config())
    window._start_extraction = MagicMock()

    window.dropEvent(_drop_event(["/tmp/sample.pdf"]))

    window._start_extraction.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_picker.py -v`
Expected: FAIL — `AttributeError: 'FilePickerWindow' object has no attribute '_is_valid_drag'` (and similar) on every test, since none of the drag/drop overrides exist yet.

- [ ] **Step 3: Add drag-and-drop support to `FilePickerWindow`**

In `gui/file_picker.py`, change the imports at the top of the file:

```python
from PyQt6.QtGui import QCloseEvent
```

to:

```python
from PyQt6.QtGui import QCloseEvent, QDragEnterEvent, QDragLeaveEvent, QDropEvent
```

Then change the class declaration and start of `__init__`:

```python
class FilePickerWindow(QWidget):
    def __init__(self, config: Config, config_path: Path | None = None) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._download_worker = None
        self.setWindowTitle("chem4all")
        self.setMinimumWidth(440)
```

to:

```python
class FilePickerWindow(QWidget):
    _DRAG_HIGHLIGHT_STYLESHEET = "FilePickerWindow { border: 2px dashed #0d6efd; }"

    def __init__(self, config: Config, config_path: Path | None = None) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._download_worker = None
        self.setWindowTitle("chem4all")
        self.setMinimumWidth(440)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
```

(`WA_StyledBackground` is required for a plain `QWidget`, unlike `QFrame`, to paint a stylesheet border — same reasoning as the existing `_RecordRow` hover-highlight feature in `gui/review_window.py`.)

Then insert the following methods immediately after the existing `_open_file` method (right before `_open_settings`):

```python
    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Chemistry Documents (*.pptx *.docx);;All Files (*)",
        )
        if path:
            self._start_extraction(Path(path))

    def _is_valid_drag(self, event: QDragEnterEvent | QDropEvent) -> bool:
        if not self._open_btn.isEnabled():
            return False
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return False
        return Path(urls[0].toLocalFile()).suffix.lower() in (".docx", ".pptx")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_valid_drag(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._DRAG_HIGHLIGHT_STYLESHEET)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet("")
        if not self._is_valid_drag(event):
            event.ignore()
            return
        path = Path(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()
        self._start_extraction(path)

    def _open_settings(self) -> None:
```

(Only the new methods are inserted between `_open_file` and `_open_settings` — `_open_settings` and everything else in the file is unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_file_picker.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest -v`
Expected: PASS (no regressions in other test files)

- [ ] **Step 6: Commit**

```bash
git add gui/file_picker.py tests/test_file_picker.py
git commit -m "Add drag-and-drop file open to file picker window"
```

---

### Task 2: Manual verification

**Files:** none (manual QA only, no code changes)

- [ ] **Step 1: Launch the app**

Run the app per the project's normal launch method (see `gui/app.py` / `main.py`).

- [ ] **Step 2: Verify valid drag-and-drop**

Drag a `.docx` file from Finder onto the `FilePickerWindow`. Confirm:
- While hovering with the file over the window, a dashed blue border appears.
- Dropping the file clears the border and starts extraction (status label/progress bar appear), identical to what happens when picking the same file via "Open File…".

Repeat with a `.pptx` file.

- [ ] **Step 3: Verify rejected drags**

- Drag a non-document file (e.g. a `.pdf` or `.png`) onto the window — confirm no highlight appears and nothing happens on drop.
- Select two `.docx` files in Finder and drag both onto the window together — confirm no highlight appears and nothing happens on drop.
- Start a model download (if the model isn't already downloaded) or an extraction, and while it's in progress, try dragging a valid `.docx` onto the window — confirm no highlight appears and the drop is ignored, matching the disabled "Open File…" button.

- [ ] **Step 4: Verify the button still works**

Click "Open File…" and confirm the file dialog still opens and extraction still proceeds normally, unaffected by this change.

- [ ] **Step 5: Report result**

No commit for this task — it's verification only. If an issue is found, fix it in Task 1 and re-commit there rather than adding a new task.
