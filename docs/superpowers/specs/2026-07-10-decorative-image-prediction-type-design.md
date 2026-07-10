# Decorative Image Prediction Type Design

## Problem

The Select Images modal lets a user pick, per image, one or more prediction
types (SMILES, IUPAC Name, Common Name, Describe Image). Some images in a
document are purely decorative — logos, dividers, backgrounds — and should
not be sent through chemical-structure identification or description at all.
Today the only way to exclude an image from processing is to uncheck its
"include" checkbox entirely, which removes it from the Review screen too.
Users want to mark an image as decorative, skip all prediction work for it,
and still have it show up in Review with an obvious, editable placeholder
value ("Decorative Image") that can be exported as alt text like any other
result.

## Scope

- `models/image_record.py` — `result_lines()` special-cases a new
  `"decorative"` prediction type.
- `gui/selection_window.py` — new `Decorative` checkbox per row, positioned
  before the other four prediction checkboxes but visually grouped with the
  image via a divider; mutually exclusive with the other four.
- `gui/worker.py` — no code change (decorative records fall through existing
  branches as a no-op).
- `gui/review_window.py` — no code change (already renders `result_lines()`
  generically).
- Tests: `tests/test_image_record.py`, `tests/test_selection_window.py`.

Out of scope: any special accessibility handling of decorative alt text in
`pipeline/writer.py` (e.g. writing an empty `descr` or a PowerPoint/Word
"mark as decorative" flag). The literal string "Decorative Image" (or the
user's edit of it) is written as alt text through the existing
`is_chemical`/`approved_value` path, unchanged.

## Data model (`models/image_record.py`)

No new field. `result_lines()` gains a special case checked before the
existing per-type lookup:

```python
_DECORATIVE_TEXT = "Decorative Image"

def result_lines(self) -> list[str]:
    if "decorative" in self.prediction_types:
        return [_DECORATIVE_TEXT]
    field_for_type = { ... }  # unchanged
    return [...]
```

Since the selection window enforces decorative as mutually exclusive with
the other four types, `prediction_types` will only ever be exactly
`["decorative"]` when this path is taken, but the check is written as a
membership test (not equality) so it degrades gracefully if that invariant
is ever violated by hand-edited review JSON.

## Selection window (`gui/selection_window.py`)

`_SelectionRow` layout order becomes:

```
[include checkbox] [thumbnail] [source ref] [Decorative] | [SMILES] [IUPAC] [Common Name] [Describe Image]
```

A `QCheckBox("Decorative")` is added immediately after the source-ref label,
followed by a `QFrame` configured as a vertical line (`QFrame.Shape.VLine`)
plus normal layout spacing, then the four existing checkboxes unchanged.
This keeps Decorative positioned before the other prediction options while
reading as grouped with the image rather than with the prediction-type
group.

Behavior:

- On checking Decorative: snapshot the current checked state of the four
  other checkboxes, uncheck all four, and disable them.
- On unchecking Decorative: re-enable the four checkboxes and restore the
  snapshotted checked state (not a fixed default).
- The snapshot is initialized to the row's starting default (`[True, False,
  False, False]` for SMILES/IUPAC/Common Name/Describe) so restoring after a
  check/uncheck with no prior interaction reproduces today's default.

**Amendment (2026-07-10):** The row's starting default is now Decorative
checked, not SMILES. All four other checkboxes start unchecked. Construction
sets up the checkboxes unchecked, wires `_decorative_check.stateChanged` to
`_on_decorative_toggled` as before, then calls
`self._decorative_check.setChecked(True)` — this routes through the same
snapshot-then-disable logic already built for user toggling, so no new
state-tracking is introduced. The snapshot taken at construction time is
therefore `[False, False, False, False]`, and unchecking Decorative with no
prior manual interaction restores that all-unchecked state (the user chose
this over falling back to SMILES-checked) — the row is then invalid until
the user manually picks a type, same validation path as today.

`prediction_types` property:

```python
@property
def prediction_types(self) -> list[str]:
    if self._decorative_check.isChecked():
        return ["decorative"]
    types = []
    if self._smiles_check.isChecked():
        types.append("smiles")
    ...
    return types
```

`connect_changed` additionally wires `self._decorative_check.stateChanged`
to the passed slot, so `SelectionWindow._update_identify_btn` re-evaluates
on toggle. No change to `_update_identify_btn` itself is needed — a row with
Decorative checked reports `prediction_types == ["decorative"]`, which is
non-empty and already satisfies the existing "at least one type checked"
validation.

## Worker (`gui/worker.py`)

No code change. The per-record dispatch is:

```python
types = set(record.prediction_types)
if types & {"smiles", "iupac", "trivial"}:
    ...
if "description" in types:
    ...
```

`{"decorative"}` intersects neither branch condition, so a decorative
record's iteration does nothing but clear `recognition_bytes` and emit
`record_ready` — satisfying "decorative images will not be processed for
predicted values" without a new code path.

## Review window (`gui/review_window.py`)

No code change. `_RecordRow` already builds its editable text from
`"\n\n".join(record.result_lines())` generically (per the prior
multi-prediction-selection design). For a decorative record this composes to
`"Decorative Image"`, which is editable and restorable via the existing
"↺ Restore predicted value" button exactly like any other prediction result.

## Error handling

No new failure modes: decorative records do no network/model calls, so
there is nothing to catch. Existing per-row validation banner logic in the
selection window is reused unchanged.

## Testing

- `tests/test_image_record.py`: add a case asserting
  `ImageRecord(..., prediction_types=["decorative"]).result_lines() ==
  ["Decorative Image"]`.
- `tests/test_selection_window.py`: add cases asserting
  - checking Decorative unchecks and disables the other four checkboxes,
    and `prediction_types == ["decorative"]`;
  - unchecking Decorative after having IUPAC checked restores IUPAC to
    checked (and re-enables all four);
  - a row with Decorative checked satisfies validation (Identify button
    enabled, error banner hidden) without any of the other four checked.
