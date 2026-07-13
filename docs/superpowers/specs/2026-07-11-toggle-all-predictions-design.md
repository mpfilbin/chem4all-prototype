# Toggle All Predictions (Select Images Screen)

## Problem

On the Select Images screen (`gui/selection_window.py`), each row
(`_SelectionRow`) has its own Decorative / SMILES / IUPAC Name / Common Name /
Describe Image checkboxes. With many images, there's no way to set a
prediction type across every row at once — only "Select All" / "Select None"
for the row-inclusion checkbox exist today. Users have to click through every
row individually to, say, turn SMILES on for all of them.

## Goals

1. One button per prediction type (Decorative, SMILES, IUPAC, Common,
   Describe) that sets that type's checkbox across every row in one click.
2. Each button is a smart toggle: if every row currently has that type
   checked, clicking it unchecks all of them; otherwise it checks all of
   them.
3. Turning a non-Decorative type on for all rows must not violate the
   existing Decorative/other mutual-exclusion rule — any row's Decorative
   checkbox gets cleared first.
4. Buttons are positioned near "Select All" / "Select None", each visually
   forming a column with its corresponding checkbox below it.

## Non-goals

- No change to "Select All" / "Select None" (row-inclusion checkbox) behavior.
- No persistence of toggle state across window instances.
- No change to `ImageRecord` or downstream recognition/review code —
  `prediction_types` already reflects whatever the checkboxes end up as.

## Design

### Toggle logic — `_SelectionRow` (`gui/selection_window.py`)

Add two public methods so `SelectionWindow` doesn't need to reach into
`_SelectionRow`'s private checkboxes or re-implement the mutual-exclusion
rule:

```python
_TYPE_ATTR = {
    "decorative": "_decorative_check",
    "smiles": "_smiles_check",
    "iupac": "_iupac_check",
    "trivial": "_trivial_check",
    "description": "_describe_check",
}

def is_type_checked(self, pred_type: str) -> bool:
    return getattr(self, self._TYPE_ATTR[pred_type]).isChecked()

def set_type_checked(self, pred_type: str, checked: bool) -> None:
    if pred_type == "decorative":
        self._decorative_check.setChecked(checked)
        return
    if checked and self._decorative_check.isChecked():
        self._decorative_check.setChecked(False)  # restores/re-enables the others
    getattr(self, self._TYPE_ATTR[pred_type]).setChecked(checked)
```

Setting Decorative checked already disables/clears the other four
(`_on_decorative_toggled`), so `set_type_checked("decorative", True)` needs no
extra handling. Setting Decorative unchecked already restores whatever the
other four previously were — accepted as-is, consistent with today's
single-row behavior.

### `SelectionWindow` — toggle-all handler

```python
def _toggle_all_type(self, pred_type: str) -> None:
    if not self._rows:
        return
    all_checked = all(row.is_type_checked(pred_type) for row in self._rows)
    target = not all_checked
    for row in self._rows:
        row.set_type_checked(pred_type, target)
```

Wired to 5 buttons, one per `pred_type` in
`["decorative", "smiles", "iupac", "trivial", "description"]`.

### Layout

A new `QHBoxLayout` row is added directly below the existing "Select All" /
"Select None" row (its own row, not merged into that one).

Button labels: "Toggle All Decorative", "Toggle All SMILES", "Toggle All
IUPAC", "Toggle All Common", "Toggle All Describe".

**Column alignment.** `_SelectionRow`'s internal layout order is: include
checkbox → 72px thumbnail → expanding source-ref label → Decorative checkbox
→ divider → SMILES/IUPAC Name/Common Name/Describe Image checkboxes. The
toggle-button row mirrors this shape so each button lands above its
checkbox:

- Invisible spacer widgets matching the include-checkbox's `sizeHint()`
  width and the 72px thumbnail width, then a `addStretch()` matching the
  expanding label.
- For each of the 5 columns, compute
  `width = max(QCheckBox(label).sizeHint().width(), QPushButton(button_text).sizeHint().width())`
  using throwaway measurement widgets. Apply this as `setFixedWidth` to
  *both* the header button and the corresponding checkbox on every
  `_SelectionRow` (a new `apply_column_widths(widths: dict[str, int])`
  method on `_SelectionRow`, called once per row after construction).
  Since button labels ("Toggle All SMILES") are wider than checkbox labels
  ("SMILES"), this widens the checkbox columns — the checkbox stays
  left-aligned with blank trailing space, and the button (which
  center-aligns text by default) sits centered over the same width.
- A fixed-width spacer approximating the divider + inter-item gap, tuned by
  eye via an offscreen screenshot (see Testing) rather than derived
  analytically — exact sub-pixel matching there isn't worth the
  complexity.

**Scrollbar stability.** The row list lives in a `QScrollArea` below the
button row; if its scrollbar only appears once there are enough images, row
content width shifts relative to the header by the scrollbar's width. Set
`scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)` so
alignment is stable regardless of image count. Also zero out
`container_layout`'s content margins so rows start flush with the scroll
viewport edge, matching the button row's own left inset.

## Testing

Extend `tests/test_selection_window.py` (existing pattern: offscreen
`QApplication`, direct construction, no `pytest-qt`):

- `_toggle_all_type` checks all rows when none/some are checked for a type,
  and unchecks all rows when all are already checked (both Decorative and a
  non-Decorative type).
- Toggling a non-Decorative type on for all rows clears Decorative on any
  row that had it checked (and re-enables/restores that row's other
  checkboxes per existing behavior).
- Toggling Decorative on for all rows clears/disables the other four on
  every row.
- `is_type_checked` / `set_type_checked` round-trip for each `pred_type`.

Also manually verified by running the app offscreen
(`QT_QPA_PLATFORM=offscreen`) and grabbing a screenshot to check button/
checkbox column alignment, adjusting the divider-gap constant if needed.
