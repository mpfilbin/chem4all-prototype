# Editable Predicted Value Field (Review Screen)

## Problem

On the Review screen, each record shows two separate text boxes: a read-only
"Predicted SMILES" (or IUPAC/Common Name/Description) field, and a "Custom
override" `QLineEdit` below it. Users who want to correct a prediction have to
retype the whole value into the override box rather than editing the
prediction in place. The predicted-value box is also fixed at a height that
doesn't comfortably show multi-line values.

## Goals

1. Merge the predicted-value box and the override box into a single editable
   field.
2. Size that field to ~4 lines of text, scrolling internally beyond that.
3. Persist user edits across Previous/Next page navigation.
4. Don't let a late-arriving async prediction clobber an in-progress user edit.
5. Provide a way to undo an accidental clear of the field.

## Non-goals

- No changes to the underlying `ImageRecord` data model.
- No new automated GUI test infrastructure (see Testing below).

## Design

### Component changes (`gui/review_window.py`, `_RecordRow`)

- Remove `_override_field` (`QLineEdit`) and its "Custom override:" label.
- Rename `_result_field` → `_value_field`. Remove `setReadOnly(True)` so it's
  directly editable. Keep the existing type-specific label
  (`_TYPE_LABELS`) unchanged.
- Set `_value_field`'s fixed height from font metrics so ~4 lines are visible
  (`fontMetrics().lineSpacing() * 4 + frame/margin padding`), keeping
  `LineWrapMode.WidgetWidth`. Qt's default "as needed" vertical scrollbar
  policy already provides scrolling beyond that height — no policy change
  needed.
- Add a small "↺ Restore predicted value" `QPushButton` below `_value_field`.
  Hidden (or disabled) whenever the field's text matches the original
  prediction; shown/enabled otherwise.

### `ReviewWindow` changes

- Add one persistent hint banner (`QLabel`), styled similarly to the existing
  status bar, placed above the scroll area (below the existing status bar).
  Static text, e.g.: "Predicted values are editable — edit a field to
  override the prediction in the exported file. Clearing a field excludes
  that image; use Restore to undo."

### Data flow / persistence

- `ImageRecord.approved_value` remains the sole field written to disk; no
  model changes.
- On construction, `_RecordRow` pre-fills `_value_field` with:
  `record.approved_value if record.approved_value is not None else record.result_value()`.
  This is how edits survive Previous/Next: rows are rebuilt per page, but
  `apply_to_record()` already runs on every page transition and writes the
  current field text back to `record.approved_value` before the row is torn
  down.
- `apply_to_record()` becomes:
  ```python
  def apply_to_record(self) -> None:
      value = self._value_field.toPlainText().strip()
      self._record.approved_value = value
      self._record.is_chemical = bool(value)
  ```
  An emptied field yields `approved_value == ""` and `is_chemical = False`,
  matching today's semantics for "no usable value" — the record is excluded
  from output.

### Race condition: async prediction vs. in-progress edit

- `_RecordRow` tracks `self._edited = False`.
- All programmatic writes to `_value_field` (initial fill, `update_record`,
  Restore) wrap `setPlainText` in `blockSignals(True)` / `blockSignals(False)`
  so they don't count as user edits.
- Connect the field's `textChanged` signal to a handler that sets
  `self._edited = True`. Because programmatic updates are signal-blocked,
  this only fires for genuine user keystrokes.
- `update_record()` (invoked from `on_record_ready` as predictions stream in)
  only calls `setPlainText(...)` when `not self._edited`. Once a user has
  typed anything in a row, later async updates for that row are ignored.

### Restore button behavior

- Visibility/enabled state is recomputed on every `textChanged`: shown when
  `_value_field.toPlainText() != (record.result_value() or "")`, hidden
  otherwise. This covers both "edited to a different value" and "emptied."
- Clicking it: signal-blocked `setPlainText(record.result_value() or "")`,
  then reset `self._edited = False` (a restored field is, again, the
  unedited state, so a later async update would be allowed to refresh it —
  consistent with the pre-edit row).

## Testing

`gui/review_window.py` has no existing widget-level tests and the project
doesn't depend on `pytest-qt`. Consistent with current practice, this change
is verified manually by running the app (typing edits, clearing a field and
using Restore, navigating Previous/Next, and confirming an in-progress edit
survives a simulated late prediction) rather than adding new GUI test
infrastructure.
