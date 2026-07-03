# Design: Image Description for Non-Chemical Images

## Context

chem4all currently identifies chemical structures and predicts SMILES, IUPAC names, or common names. Some images in course materials — cell membranes, organelles, biochemical pathways — are not chemical structures and cannot be identified by DECIMER. This feature adds a "Describe Image" mode that uses GPT-4o vision (via the already-configured OpenRouter API) to generate a single-sentence alt-text description for any image.

## Pipeline Before / After

**Before:** extract → select (SMILES / IUPAC / Common Name per image) → recognize (DECIMER → optional name lookup) → review

**After:** extract → select (SMILES / IUPAC / Common Name / Describe Image per image) → recognize (DECIMER path OR vision description path, based on type) → review

---

## Section 1 — Data Model (`models/image_record.py`)

Add field:
```python
description: str | None = None
```

Extend `result_value()`:
```python
def result_value(self) -> str | None:
    if self.prediction_type == "description":
        return self.description
    if self.prediction_type == "iupac":
        return self.iupac_name
    if self.prediction_type == "trivial":
        return self.trivial_name
    return self.predicted_smiles
```

Update `to_review_dict()` to include `"description": self.description`.

Update `from_review_dict()` to restore `description=d.get("description")`.

`"description"` becomes the fourth valid `prediction_type` string alongside `"smiles"`, `"iupac"`, `"trivial"`.

---

## Section 2 — Pipeline (`pipeline/describer.py`)

New file following the same pattern as `pipeline/namer.py`:

```python
_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = (
    "You are an educational accessibility assistant. Given an image from a science "
    "course, respond with a single sentence suitable for use as alt-text. Describe "
    "what is depicted and its scientific significance."
)

def describe_image(image_bytes: bytes, api_key: str) -> str:
    resolved_key = os.environ.get("OPENROUTER_API_KEY") or api_key
    if not resolved_key:
        raise RuntimeError("No OpenRouter API key configured.")
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"
    response = requests.post(
        _ENDPOINT,
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "chem4all",
        },
        json={
            "model": "openai/gpt-4o",
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]},
            ],
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"OpenRouter returned {response.status_code}: {response.text}")
    return response.json()["choices"][0]["message"]["content"].strip()
```

Tests in `tests/test_describer.py` monkeypatch `requests.post`:
- success — correct payload sent, returns stripped description
- env var takes precedence over api_key arg
- no key raises RuntimeError
- non-200 response raises RuntimeError
- `requests.RequestException` raises RuntimeError

---

## Section 3 — Worker (`gui/worker.py`)

At the top of the per-image loop, before the DECIMER path:

```python
if record.prediction_type == "description":
    self.status.emit(f"Describing {record.source_ref}  ({i + 1} of {total})…")
    try:
        record.description = describe_image(record.recognition_bytes, api_key)
    except Exception as exc:
        log.warning("Description failed for %s: %s", record.source_ref, exc)
        self.error.emit(f"Could not describe {record.source_ref}: {exc}")
    finally:
        record.recognition_bytes = b""
    self.progress.emit(i + 1, total)
    self.record_ready.emit(record)
    continue
```

The existing SMILES → optional name lookup block is unchanged and runs only for `"smiles"`, `"iupac"`, and `"trivial"` types.

---

## Section 4 — Selection Window (`gui/selection_window.py`)

`_SelectionRow` gains a fourth radio button in the existing `_type_group`:

```python
self._describe_radio = QRadioButton("Describe Image")
self._type_group.addButton(self._describe_radio)
layout.addWidget(self._describe_radio)
```

`prediction_type` property gains one branch:

```python
if self._describe_radio.isChecked():
    return "description"
```

No other changes — `_start_identification` already stamps `record.prediction_type = row.prediction_type` generically.

---

## Section 5 — Review Window (`gui/review_window.py`)

`_TYPE_LABELS` dict gains one entry:

```python
_TYPE_LABELS = {
    "iupac": "IUPAC Name:",
    "trivial": "Common Name:",
    "description": "Image Description:",
}
```

No other changes — `_RecordRow` already displays `result_value()` in a read-only `QTextEdit` with a custom override field, which works identically for descriptions.

---

## Testing

- `tests/test_describer.py` — 5 new tests (see Section 2)
- `tests/test_image_record.py` — add `description` default assertion, `result_value()` for `"description"` type, serialization roundtrip
- No changes needed to existing namer or recognizer tests

```bash
python -m pytest tests/ -v
```
