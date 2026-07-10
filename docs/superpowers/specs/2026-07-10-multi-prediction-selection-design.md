# Multi-Prediction Selection Design

## Problem

The Select Images modal lets the user pick, per image, exactly one prediction
type (SMILES, IUPAC Name, Common Name, or Describe Image) via a radio-button
group. Users want to request several prediction types for the same image in
one pass (e.g. SMILES *and* IUPAC Name *and* a description), with all results
shown together in the Review view's result field.

Separately, the Review view's result text field is always editable, even
while that image's predictions are still in flight. If a user types into the
field before the worker finishes, their edit can be silently overwritten when
the result arrives (guarded today only by an "edited" flag set on any text
change). We want the field locked (read-only) until every prediction
requested for that image has returned.

## Scope

- `gui/selection_window.py` — checkboxes instead of radio buttons, per-row
  validation.
- `models/image_record.py` — `prediction_type: str` → `prediction_types:
  list[str]`, `result_value()` → `result_lines()`.
- `gui/worker.py` — run the union of work implied by the selected types per
  record, emit `record_ready` once per record after all its selected work is
  attempted.
- `gui/review_window.py` — per-row read-only lock until that record's
  `record_ready` has fired; generic result label; multi-line composed text.
- `pipeline/reviewer.py` — no code change; JSON shape changes via
  `to_review_dict`/`from_review_dict`.
- Tests: `tests/test_image_record.py`, `tests/test_worker.py`.

Out of scope: relaxing the existing whole-batch gate on Prev/Next/Accept
(unchanged — those stay disabled until every record in the batch has
returned, regardless of this feature). No backward compatibility with
previously saved review JSON files using the old single `prediction_type`
field — this is a breaking format change and that's acceptable.

## Data model

`models/image_record.py`:

```python
prediction_types: list[str] = field(default_factory=lambda: ["smiles"])
```

`result_value()` is replaced with:

```python
_TYPE_ORDER = ["smiles", "iupac", "trivial", "description"]

def result_lines(self) -> list[str]:
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

The Review view joins `result_lines()` with `"\n"` for display — raw values,
no per-line labels (per user's choice).

`to_review_dict`/`from_review_dict` serialize `prediction_types` as a JSON
list under the same key name shape convention (`"prediction_types": [...]`).
`from_review_dict` reads `d.get("prediction_types", ["smiles"])` — no
fallback for the old singular key.

## Selection window (`gui/selection_window.py`)

`_SelectionRow` replaces its `QRadioButton` × 4 + `QButtonGroup` with 4
independent `QCheckBox`es (SMILES, IUPAC Name, Common Name, Describe Image).
SMILES starts checked; the others start unchecked (matches today's default
selection). A `prediction_types` property returns the checked ones in fixed
order (`["smiles", "iupac", "trivial", "description"]` filtered to checked).

Each checkbox's `stateChanged` connects to the same validation/update path as
the include checkbox.

`SelectionWindow` adds a hidden-by-default error banner `QLabel` (dark red
text on light red background, consistent with existing banner styling
patterns) below the header. `_update_identify_btn` (renamed in spirit but
kept as the single validation entry point) now:

1. Counts included rows (`n`) as before.
2. Checks whether any included row has zero prediction-type checkboxes
   checked.
3. If any such row exists: disable the Identify button, show the banner with
   text "Each selected image needs at least one prediction type checked."
4. Otherwise: hide the banner, enable the Identify button if `n > 0`, keep
   the existing "Identify Selected (n) →" label.

`_start_identification` sets `record.prediction_types = row.prediction_types`
(a list) instead of a single string.

## Worker (`gui/worker.py`)

Per record, replace the `if record.prediction_type == "description": ... continue`
branch structure with a single pass that runs the union of needed work:

```python
types = set(record.prediction_types)
try:
    if types & {"smiles", "iupac", "trivial"}:
        self.status.emit(f"Identifying {record.source_ref} ({i+1} of {total})…")
        try:
            smiles, confidence = _run_decimer(record.recognition_bytes)
            record.predicted_smiles = smiles
            record.confidence = confidence
        except Exception as exc:
            self.error.emit(f"Could not identify {record.source_ref}: {exc}")
            smiles = None

        if "iupac" in types and smiles:
            self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
            try:
                record.iupac_name = lookup_iupac(smiles, api_key)
            except Exception as exc:
                self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

        if "trivial" in types and smiles:
            self.status.emit(f"Looking up common name for {record.source_ref}…")
            try:
                record.trivial_name = lookup_trivial_name(smiles, api_key)
            except Exception as exc:
                self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

    if "description" in types:
        self.status.emit(f"Describing {record.source_ref} ({i+1} of {total})…")
        try:
            record.description = describe_image(record.recognition_bytes, api_key)
        except Exception as exc:
            self.error.emit(f"Could not describe {record.source_ref}: {exc}")
finally:
    record.recognition_bytes = b""

self.progress.emit(i + 1, total)
self.record_ready.emit(record)
```

Each stage keeps its own try/except so a failure in one lookup (e.g. IUPAC
lookup failing) doesn't prevent the others (e.g. description) from running;
failures continue to call `self.error.emit(...)` as today. `record_ready` is
emitted exactly once per record, after every requested stage has been
attempted — this single emission is the signal the Review window uses to
unlock that row's field.

## Review window (`gui/review_window.py`)

`ReviewWindow` gains `self._done_ids: set[str]`, populated in
`on_record_ready` before locating and updating the matching row.

`_RecordRow.__init__` takes an additional `done: bool` argument:

- **`done=False`**: `QTextEdit` constructed with `setReadOnly(True)`,
  placeholder "Awaiting result…", restore button hidden, `_edited=False`.
- **`done=True`**: `QTextEdit` editable, initial text is `approved_value` if
  set else `"\n".join(record.result_lines())`.

`_render_page` passes `record.id in self._done_ids` when constructing each
row.

`update_record(record)` (called from `on_record_ready` for a currently
visible row) additionally calls `setReadOnly(False)` and, if the row was not
yet marked done, populates the composed text — mirroring the existing
"don't clobber user edits" guard (`if not self._edited`).

The per-type `_TYPE_LABELS` dict and its lookup are removed; the field label
becomes a fixed `QLabel("Prediction Results:")`.

## Error handling

- Worker-side per-stage failures behave as today: caught individually,
  reported via `self.error.emit(...)`, and don't stop the other stages for
  that record or the rest of the batch.
- Selection-window validation is purely a UI gate (disabled button + banner)
  — no exceptions, nothing to catch.

## Testing

- `tests/test_image_record.py`: replace `prediction_type`/`result_value`
  tests with `prediction_types`/`result_lines` equivalents, including a
  multi-type case (e.g. `["iupac", "description"]` returns both values in
  order, skipping unset/unselected types).
- `tests/test_worker.py`: update `_make_record` to take `prediction_types`
  (list). Add a case asserting that a record with `["iupac", "description"]`
  produces both an IUPAC lookup and a description, does not perform a trivial
  lookup, and emits exactly one `record_ready`.
