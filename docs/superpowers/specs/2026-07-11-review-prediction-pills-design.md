# Prediction-Type Pills (Review Screen)

## Problem

On the Review screen (`gui/review_window.py`), each `_RecordRow` shows a
"Prediction Results:" label above the editable results text box, but gives no
indication of *which* prediction types (SMILES, IUPAC, Trivial, Description,
Decorative) were actually requested for that image. The user has to infer it
from the composed text itself.

## Goals

1. Show a compact, colored "pill" per requested prediction type, floating to
   the right of the "Prediction Results:" label on the same line.
2. Each prediction type has a distinct, fixed background color so types are
   visually distinguishable at a glance across rows.
3. Consistent left-to-right ordering of pills regardless of the order types
   happen to be stored in `ImageRecord.prediction_types`.

## Non-goals

- No interactivity — pills are static (no tooltip, no click behavior).
- No legend/key explaining the colors elsewhere in the UI.
- No theme-derived colors — pill colors are fixed regardless of light/dark
  system theme (only the label text elsewhere in the app is theme-aware).
- No change to `ImageRecord`, `SelectionWindow`, or how `prediction_types` is
  populated — this is a pure display addition on the Review screen.

## Design

### Pill styling and ordering — `gui/review_window.py`

Module-level constants, ordered independent of storage order in
`prediction_types`:

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
```

Colors are fixed hex values (white text on each), matching the app's
existing bootstrap-ish palette already used for the status banners in this
file. `"decorative"` is mutually exclusive with the other four types
(enforced today in `SelectionWindow`), so it only ever renders as a lone
pill — no special-casing needed beyond iterating `_PILL_ORDER`.

A helper builds one pill:

```python
def _make_pill(pred_type: str) -> QLabel:
    pill = QLabel(_PILL_LABELS[pred_type])
    pill.setStyleSheet(
        f"background-color: {_PILL_COLORS[pred_type]}; color: white; "
        "border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
    )
    return pill
```

### Layout — `_RecordRow.__init__`

Replace the standalone label line:

```python
info.addWidget(QLabel("Prediction Results:"))
```

with a header row combining the label and right-floated pills:

```python
header_row = QHBoxLayout()
header_row.addWidget(QLabel("Prediction Results:"))
header_row.addStretch()
for pred_type in _PILL_ORDER:
    if pred_type in record.prediction_types:
        header_row.addWidget(_make_pill(pred_type))
info.addLayout(header_row)
```

### No refresh needed on recognition completion

`record.prediction_types` is fixed before `ReviewWindow` is ever
constructed — `SelectionWindow._start_identification` sets
`row.record.prediction_types = row.prediction_types` before building the
selected list, and nothing downstream mutates it afterward. Pills are
therefore built once at `_RecordRow` construction time and require no
handling in `update_record()` (which only runs when a background
recognition result arrives for that record).

## Testing

Extend `tests/test_review_window.py` if it exists (or the equivalent review
window test module):

- A row constructed with `prediction_types = ["smiles", "iupac"]` produces
  pills labeled "SMILES" and "IUPAC", in that order, and no others.
- A row with `prediction_types = ["decorative"]` produces exactly one pill,
  labeled "Decorative".
- Pill order is independent of the order types appear in
  `prediction_types` (e.g. `["description", "smiles"]` still renders SMILES
  before Description).

Also manually verified by running the app (`/run` or offscreen
`QT_QPA_PLATFORM=offscreen`) and checking pill placement/colors visually on
the Review screen for a few different type combinations.
