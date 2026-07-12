# Drag-and-Drop Hint Label (File Picker Window)

## Problem

`FilePickerWindow` (`gui/file_picker.py`) now supports dragging a `.docx`/
`.pptx` file onto the window to open it (see
`docs/superpowers/specs/2026-07-12-drag-and-drop-file-open-design.md`), but
nothing in the UI tells the user this is possible. The only visible
instruction is "Open a PPTX or DOCX file to begin.", which reads as
click-only.

## Goals

1. A small, persistent notice on `FilePickerWindow` tells the user they can
   drag and drop a file onto the window, in addition to using "Open File…".
2. The notice is visible at all times the window is open — not gated on
   extraction/download state.

## Non-goals

- No changes to any other window.
- No changes to the drag-and-drop behavior itself (validation, highlight,
  extraction) — this is copy/UI only.

## Design

### `FilePickerWindow.__init__` (`gui/file_picker.py`)

Add a new `QLabel` as the last widget added to the window's `QVBoxLayout`,
after `self._extract_count_label` (currently the last widget added):

```python
self._drag_hint_label = QLabel("You can also drag and drop a file here to open it.")
self._drag_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
self._drag_hint_label.setStyleSheet("QLabel { color: #6c757d; font-size: 11px; }")
layout.addWidget(self._drag_hint_label)
```

This reuses the exact stylesheet already applied to `_model_load_label`
(`gui/file_picker.py:29`), so it reads as the same "small caption" style
already established in this window — no new color/size introduced.

Because it's appended last, it renders below the (normally hidden)
status/progress/count widgets, staying at the visual bottom of the window
in both the idle and busy states. Unlike those widgets, it is never
`.hide()`/`.show()`'d — it's always visible.

## Testing

No new test file — this is a static label with no conditional
show/hide logic to unit test (unlike the drag-and-drop accept/reject logic,
which already has coverage in `tests/test_file_picker.py`). Verify manually:
launch the app and confirm the label renders at the bottom of the window,
in both the idle state and while extraction is in progress.
