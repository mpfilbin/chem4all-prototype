# Design: Per-Image Prediction Type Selection

## Context

Previously, the Review screen let users look up IUPAC or common names on demand after SMILES recognition had already completed. This created a multi-step, click-heavy review flow. The goal of this change is to move prediction type selection earlier in the pipeline — to the Select Images screen — so the user declares intent upfront, the worker runs the full pipeline automatically, and the Review screen shows only the final result plus an optional override.

## Pipeline Before / After

**Before:** extract → select (checkbox only) → recognize (SMILES) → review (SMILES + on-demand IUPAC/common lookup + radio selection)

**After:** extract → select (checkbox + prediction type) → recognize (SMILES → optional name lookup, based on type) → review (final result + custom override only)

---

## Section 1 — Data Model (`models/image_record.py`)

Add field:
```python
prediction_type: str = "smiles"   # "smiles" | "iupac" | "trivial"
```

Add method:
```python
def result_value(self) -> str | None:
    if self.prediction_type == "iupac":
        return self.iupac_name
    if self.prediction_type == "trivial":
        return self.trivial_name
    return self.predicted_smiles
```

Update `to_review_dict()` and `from_review_dict()` to include `prediction_type`.

Existing fields `predicted_smiles`, `iupac_name`, `trivial_name` are retained — the worker always stores the SMILES result and additionally stores the name result in the appropriate field when a lookup is performed.

---

## Section 2 — Selection Screen (`gui/selection_window.py`)

Each image row gains a radio group:

```
[Thumbnail]  source_ref
             ◉ SMILES  ○ IUPAC Name  ○ Common Name    ☑ Include
```

- SMILES is selected by default for every row.
- The checkbox and Select All / Select None buttons are unchanged.
- The "Identify Selected (N) →" count reflects checked images regardless of prediction type.
- When "Identify Selected" is clicked: iterate selected rows, set `record.prediction_type` from that row's radio group, then pass records to `RecognizerWorker` and open `ReviewWindow` — same flow as today.

---

## Section 3 — Worker (`gui/worker.py`)

`RecognizerWorker.run()` sequence per image:

1. Emit status: `"Identifying {source_ref} ({i+1} of {total})…"`
2. Call `_run_decimer` → store `record.predicted_smiles`
3. If `prediction_type == "iupac"`:
   - Emit status: `"Looking up IUPAC name for {source_ref}…"`
   - Call `lookup_iupac(smiles, api_key)` → store in `record.iupac_name`
4. If `prediction_type == "trivial"`:
   - Emit status: `"Looking up common name for {source_ref}…"`
   - Call `lookup_trivial_name(smiles, api_key)` → store in `record.trivial_name`
5. Emit `record_ready`

API key resolved once at top of `run()`:
```python
api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
```

Name lookup failures are caught and logged; the record still emits `record_ready` with the name field left as `None`.

**Remove:** `gui/namer_worker.py` is deleted — the on-demand pattern is fully replaced by this in-worker sequence.

---

## Section 4 — Review Screen (`gui/review_window.py`)

`_RecordRow` is simplified:

```
[Thumbnail]  source_ref
             Predicted SMILES: / IUPAC Name: / Common Name:   [read-only QTextEdit]
             Custom override:  [QLineEdit]
```

- Label is determined from `record.prediction_type` at construction.
- Result field populated from `record.result_value()`; placeholder "Awaiting result…" while worker runs.
- `update_record()` refreshes the result field with `record.result_value()`.
- `apply_to_record()`:
  ```python
  override = self._override_field.text().strip()
  self._record.approved_value = override if override else self._record.result_value()
  self._record.is_chemical = bool(self._record.approved_value)
  ```

**Remove:** all four radio buttons, IUPAC lookup button, Common Name lookup button, and associated error labels.

---

## What Is Deleted

- `gui/namer_worker.py` — entire file removed
- All radio buttons and lookup buttons from `_RecordRow`
- `_start_iupac_lookup`, `_start_trivial_lookup`, `_start_name_lookup`, `_on_lookup_done`, `_on_lookup_error` methods from `_RecordRow`

---

## Testing

**Modified tests:**
- `tests/test_image_record.py` — add `prediction_type` default assertion; add `result_value()` tests for all three types
- `tests/test_namer.py` — no changes needed (pipeline functions are unchanged)

**No new test files needed** — the worker threading is tested via the existing recognizer tests; name lookup functions already have full coverage.

**Verification:**
```bash
python -m pytest tests/ -v
```
Manual: load a PPTX, select images with mixed types (one SMILES, one IUPAC, one Common Name), identify — confirm the Review screen shows the correct result type per row and that the output file alt-text reflects the chosen value.
