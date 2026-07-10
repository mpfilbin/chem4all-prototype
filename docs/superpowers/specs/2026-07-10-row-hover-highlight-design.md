# Row Hover Highlight (Select Images & Review Screens)

## Problem

The Select Images screen (`gui/selection_window.py`, `_SelectionRow`) and the
Review screen (`gui/review_window.py`, `_RecordRow`) both render one row per
image in a scrollable list. Rows have no hover feedback, so with many images
it's easy to lose track of which row the cursor is over while
checking/unchecking boxes or reading/editing text side by side.

## Goals

1. Hovering the mouse over a row on either screen tints its background,
   giving a clear visual affordance for which row is under the cursor.
2. Moving the mouse off the row reverts it to its normal (no) background.
3. Consistent behavior/color across both screens.

## Non-goals

- No changes to selection/click behavior, only a visual hover cue.
- No dark-mode variant — the app has no theme system today; all existing
  styling is fixed light-mode hex colors, and this follows that.
- No changes to other windows (file picker, settings dialog) — they aren't
  row-based lists.

## Design

### `HoverHighlightMixin` (`gui/widgets.py`)

Add a small mixin, alongside the existing `ThumbnailLabel`, that any row
widget can inherit to get hover tinting:

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

Behavior is implemented imperatively (setting/clearing a stylesheet on
enter/leave) rather than via a QSS `:hover` pseudo-class rule, matching this
codebase's existing pattern of setting stylesheets imperatively based on
state (e.g. the status bar in `review_window.py`). It's also more
deterministic to unit test.

Neither row currently sets its own stylesheet outside of this feature, so
unconditionally clearing to `""` on leave is safe and doesn't need to restore
a prior value.

### `_SelectionRow` (`gui/selection_window.py`)

Already a `QFrame`. Mix in directly:

```python
class _SelectionRow(HoverHighlightMixin, QFrame):
```

`QFrame` renders `background-color` from its stylesheet natively, no
additional attribute needed.

### `_RecordRow` (`gui/review_window.py`)

A plain `QWidget`, which does **not** paint stylesheet backgrounds by
default. Mix in the same way, and set the styled-background attribute in
`__init__`:

```python
class _RecordRow(HoverHighlightMixin, QWidget):
    def __init__(self, record: ImageRecord, done: bool, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ...
```

### Color

`#eef3fb` — a soft blue-gray tint, chosen to echo the app's existing light
status-banner blue (`#cce5ff`) without being as saturated. Same value used on
both screens.

### Visual scope

The tint covers the full row width/height (both rows already stretch to the
full width of their containing `QVBoxLayout`). Child widgets with their own
opaque backgrounds (e.g. the `QTextEdit` in `_RecordRow`) keep their own
background and simply sit on top of the tint — expected and consistent with
how the row already looks today.

## Testing

Both `_SelectionRow` and `_RecordRow` are already exercised by direct
instantiation under an offscreen `QApplication` in
`tests/test_review_window.py` (no `pytest-qt`/`qtbot`). Add unit tests
following that same pattern:

- Construct a row, call `row.enterEvent(QEvent(QEvent.Type.Enter))`, assert
  `row.styleSheet() == HoverHighlightMixin.HOVER_STYLESHEET`.
- Call `row.leaveEvent(QEvent(QEvent.Type.Leave))`, assert
  `row.styleSheet() == ""`.

Add these for `_RecordRow` in `tests/test_review_window.py` and for
`_SelectionRow` in the existing `tests/test_selection_window.py`.

Also manually verified by running the app and hovering rows on both screens.
