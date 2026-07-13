# Drag-and-Drop File Open (File Picker Window)

## Problem

The `FilePickerWindow` (`gui/file_picker.py`) is the entry point of chem4all:
the user opens a DOCX/PPTX by clicking "Open File…", which shows a
`QFileDialog`. There's no way to open a file by dragging it onto the window,
which is a common and expected affordance for a document-processing desktop
app.

## Goals

1. Dragging a single `.docx` or `.pptx` file onto the `FilePickerWindow` and
   dropping it starts extraction, identical to picking that file via "Open
   File…".
2. While dragging a valid file over the window, the window shows a visual
   highlight (accepted-drop affordance). The highlight clears on drag-leave
   or drop.
3. The existing "Open File…" button is unchanged and remains available.

## Non-goals

- No drag-and-drop support on `SelectionWindow`, `ReviewWindow`, or
  `SettingsDialog` — only the main file picker window.
- No support for dropping multiple files, folders, or non-document files —
  these are rejected (see below).
- No new dialogs/messages for rejected drops — rejection is silent (standard
  "not allowed" drag cursor), since nothing was actually dropped.

## Design

### Accept/reject rules

A drag is accepted only if **all** of the following hold:

- The window is not busy — i.e. `self._open_btn.isEnabled()` is `True`. The
  button is already disabled during model download (`_start_download`) and
  during active extraction (`_start_extraction`), so this reuses that exact
  state rather than tracking a separate busy flag.
- `event.mimeData().hasUrls()` is `True` and there is exactly one URL.
- The URL is a local file (`url.isLocalFile()`) whose suffix, lowercased, is
  `.docx` or `.pptx`.

If any condition fails, the event is ignored (`event.ignore()`) and Qt shows
the standard "not allowed" cursor. No dialog, no state change.

### `FilePickerWindow` changes (`gui/file_picker.py`)

```python
def __init__(self, ...):
    ...
    self.setAcceptDrops(True)
    self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
```

`WA_StyledBackground` is required for a plain `QWidget` (not `QFrame`) to
paint a stylesheet border — same reasoning as `_RecordRow` in the existing
hover-highlight feature.

```python
_DRAG_HIGHLIGHT_STYLESHEET = "FilePickerWindow { border: 2px dashed #0d6efd; }"

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
```

This reuses `_start_extraction`, the same method the "Open File…" button
calls, so extraction, progress UI, and error handling need no changes.

### Highlight color

`#0d6efd` (Bootstrap-style blue, dashed 2px border) — distinct from the
existing hover-tint blue (`#eef3fb`) used elsewhere, since this is a
border/outline rather than a fill, and needs to be visible against the
window's default background.

## Testing

Following the pattern in `tests/test_review_window.py` (offscreen
`QApplication`, direct instantiation, no `pytest-qt`), add
`tests/test_file_picker.py`:

- Construct a `FilePickerWindow`.
- Build a `QDragEnterEvent`/`QDropEvent` with mock `QMimeData` (via
  `QMimeData.setUrls([QUrl.fromLocalFile(...)])`) for:
  - a valid single `.docx` — asserts `_is_valid_drag` is `True`.
  - a valid single `.pptx` — asserts `_is_valid_drag` is `True`.
  - a `.pdf` — asserts `_is_valid_drag` is `False`.
  - two valid files at once — asserts `_is_valid_drag` is `False`.
  - a valid file while `self._open_btn.setEnabled(False)` — asserts
    `_is_valid_drag` is `False`.
- Call `dragEnterEvent` with a valid event, assert
  `window.styleSheet() == FilePickerWindow._DRAG_HIGHLIGHT_STYLESHEET`.
- Call `dragLeaveEvent`, assert `window.styleSheet() == ""`.
- Call `dropEvent` with a valid event and a monkeypatched/mocked
  `_start_extraction`, assert it was called with the dropped `Path` and that
  the stylesheet was cleared.

Also manually verify by running the app and dragging a `.docx`/`.pptx` from
Finder onto the window.
