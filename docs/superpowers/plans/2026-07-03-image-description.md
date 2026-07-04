# Image Description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Describe Image" pipeline mode that uses GPT-4o vision to generate a single-sentence alt-text description for non-chemical images (diagrams, organelles, biochemical pathways).

**Architecture:** `"description"` becomes the fourth `prediction_type` value. When selected, `RecognizerWorker` skips DECIMER entirely and calls a new `pipeline/describer.py` function that POSTs the image to GPT-4o vision via OpenRouter (already configured). The Review screen is unchanged — it already displays `result_value()` generically. The Select Images screen gains a fourth radio button per row.

**Tech Stack:** Python 3.12, PyQt6, requests (already in dependencies), OpenRouter API (GPT-4o vision)

## Global Constraints

- Python 3.9–3.12 (no 3.13+ syntax)
- PyQt6 only (no other Qt bindings)
- OpenRouter endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Model: `"openai/gpt-4o"` (string, not an enum)
- `prediction_type` values are plain strings: `"smiles"`, `"iupac"`, `"trivial"`, `"description"`
- API key precedence: `OPENROUTER_API_KEY` env var beats `config.openrouter_api_key`
- Description length: one sentence (enforced by the system prompt)
- pytest for all tests; no GUI unit tests

---

### Task 1: ImageRecord — add `description` field

**Files:**
- Modify: `models/image_record.py`
- Modify: `tests/test_image_record.py`

**Interfaces:**
- Produces: `ImageRecord.description: str | None = None`, `result_value()` returning `self.description` when `prediction_type == "description"`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_image_record.py`:

```python
def test_image_record_description_default():
    record = ImageRecord(
        id="x", source_ref="slide 1, shape 1",
        thumbnail_bytes=b"", recognition_bytes=b"",
    )
    assert record.description is None


def test_result_value_returns_description():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        description="Diagram of ATP synthase embedded in the inner mitochondrial membrane.",
        prediction_type="description",
    )
    assert record.result_value() == "Diagram of ATP synthase embedded in the inner mitochondrial membrane."


def test_result_value_returns_none_when_description_not_yet_loaded():
    record = ImageRecord(
        id="x", source_ref="s", thumbnail_bytes=b"", recognition_bytes=b"",
        prediction_type="description",  # description not set yet
    )
    assert record.result_value() is None
```

Also update three existing tests:

In `test_image_record_defaults`: add `assert record.description is None`

In `test_image_record_to_review_dict_excludes_bytes`: add `assert d["description"] is None`

In `test_image_record_from_review_dict_roundtrip`: add `assert restored.description is None`

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_image_record.py -v
```
Expected: failures on the new tests (AttributeError: description)

- [ ] **Step 3: Implement changes in `models/image_record.py`**

Replace the entire file:

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ImageRecord:
    id: str
    source_ref: str
    thumbnail_bytes: bytes
    recognition_bytes: bytes
    predicted_smiles: str | None = None
    confidence: float | None = None
    iupac_name: str | None = None
    trivial_name: str | None = None
    description: str | None = None
    prediction_type: str = "smiles"
    approved_value: str | None = None
    is_chemical: bool | None = None

    def result_value(self) -> str | None:
        if self.prediction_type == "description":
            return self.description
        if self.prediction_type == "iupac":
            return self.iupac_name
        if self.prediction_type == "trivial":
            return self.trivial_name
        return self.predicted_smiles

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "iupac_name": self.iupac_name,
            "trivial_name": self.trivial_name,
            "description": self.description,
            "prediction_type": self.prediction_type,
            "approved_value": self.approved_value,
            "is_chemical": self.is_chemical,
        }

    @classmethod
    def from_review_dict(cls, d: dict) -> ImageRecord:
        return cls(
            id=d["id"],
            source_ref=d["source_ref"],
            thumbnail_bytes=b"",
            recognition_bytes=b"",
            predicted_smiles=d.get("predicted_smiles"),
            confidence=d.get("confidence"),
            iupac_name=d.get("iupac_name"),
            trivial_name=d.get("trivial_name"),
            description=d.get("description"),
            prediction_type=d.get("prediction_type", "smiles"),
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_image_record.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add models/image_record.py tests/test_image_record.py
git commit -m "feat: add description field to ImageRecord"
```

---

### Task 2: pipeline/describer.py — GPT-4o vision API

**Files:**
- Create: `pipeline/describer.py`
- Create: `tests/test_describer.py`

**Interfaces:**
- Produces: `describe_image(image_bytes: bytes, api_key: str) -> str`

- [ ] **Step 1: Write failing tests**

Create `tests/test_describer.py`:

```python
import pytest
import requests as req
from unittest.mock import MagicMock, patch
from pipeline.describer import describe_image


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.ok = status < 400
    resp.status_code = status
    resp.text = text
    resp.json.return_value = {
        "choices": [{"message": {"content": f"  {text}  "}}]
    }
    return resp


def test_describe_image_success(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    image_bytes = b"fake-png-data"
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Diagram of ATP synthase complex.")) as mock_post:
        result = describe_image(image_bytes, "test-key")
    assert result == "Diagram of ATP synthase complex."
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "openai/gpt-4o"
    user_content = payload["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "image_url"
    assert user_content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_describe_image_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Cell membrane diagram.")) as mock_post:
        result = describe_image(b"img", "config-key")
    assert result == "Cell membrane diagram."
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer env-key"


def test_describe_image_no_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No OpenRouter API key"):
        describe_image(b"img", "")


def test_describe_image_non_200_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Unauthorized", 401)):
        with pytest.raises(RuntimeError, match="401"):
            describe_image(b"img", "bad-key")


def test_describe_image_network_error_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.describer.requests.post",
               side_effect=req.RequestException("timeout")):
        with pytest.raises(RuntimeError, match="Network error"):
            describe_image(b"img", "any-key")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_describer.py -v
```
Expected: ImportError (module not found)

- [ ] **Step 3: Implement `pipeline/describer.py`**

```python
from __future__ import annotations
import base64
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o"
_SYSTEM = (
    "You are an educational accessibility assistant. Given an image from a science "
    "course, respond with a single sentence suitable for use as alt-text. Describe "
    "what is depicted and its scientific significance."
)


def describe_image(image_bytes: bytes, api_key: str) -> str:
    resolved_key = os.environ.get("OPENROUTER_API_KEY") or api_key
    if not resolved_key:
        raise RuntimeError(
            "No OpenRouter API key configured. "
            "Add one in Settings or set the OPENROUTER_API_KEY environment variable."
        )
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"
    try:
        response = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "chem4all",
            },
            json={
                "model": _MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error during image description: {exc}") from exc

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter returned {response.status_code}: {response.text[:200]}"
        )

    return response.json()["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_describer.py -v
```
Expected: all 5 pass

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
python -m pytest tests/ -v
```
Expected: all pass (55 existing + 5 new = 60 total)

- [ ] **Step 6: Commit**

```bash
git add pipeline/describer.py tests/test_describer.py
git commit -m "feat: add describe_image() using GPT-4o vision via OpenRouter"
```

---

### Task 3: RecognizerWorker — description branch

**Files:**
- Modify: `gui/worker.py`

**Interfaces:**
- Consumes: `describe_image(image_bytes: bytes, api_key: str) -> str` from `pipeline/describer` (Task 2), `ImageRecord.description` (Task 1), `ImageRecord.prediction_type == "description"` (Task 1)

- [ ] **Step 1: Replace `gui/worker.py`**

```python
from __future__ import annotations
import logging
import os
from PyQt6.QtCore import QThread, pyqtSignal
from config import Config
from models.image_record import ImageRecord
from pipeline.recognizer import _run_decimer

log = logging.getLogger(__name__)


class RecognizerWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    record_ready = pyqtSignal(object)  # ImageRecord
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, records: list[ImageRecord], config: Config) -> None:
        super().__init__()
        self._records = records
        self._config = config

    def run(self) -> None:
        from pipeline.describer import describe_image
        from pipeline.namer import lookup_iupac, lookup_trivial_name
        api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
        total = len(self._records)
        for i, record in enumerate(self._records):

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

            self.status.emit(f"Identifying {record.source_ref}  ({i + 1} of {total})…")
            try:
                smiles, confidence = _run_decimer(record.recognition_bytes)
                record.predicted_smiles = smiles
                record.confidence = confidence

                if record.prediction_type == "iupac" and smiles:
                    self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                    try:
                        record.iupac_name = lookup_iupac(smiles, api_key)
                    except Exception as exc:
                        log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                elif record.prediction_type == "trivial" and smiles:
                    self.status.emit(f"Looking up common name for {record.source_ref}…")
                    try:
                        record.trivial_name = lookup_trivial_name(smiles, api_key)
                    except Exception as exc:
                        log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

            except Exception as exc:
                log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                self.error.emit(f"Could not identify {record.source_ref}: {exc}")
                record.predicted_smiles = None
                record.confidence = None
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
```

- [ ] **Step 2: Run full suite**

```bash
python -m pytest tests/ -v
```
Expected: all 60 pass

- [ ] **Step 3: Commit**

```bash
git add gui/worker.py
git commit -m "feat: RecognizerWorker skips DECIMER and calls describe_image for description type"
```

---

### Task 4: GUI — 4th radio button + review label

**Files:**
- Modify: `gui/selection_window.py`
- Modify: `gui/review_window.py`

**Interfaces:**
- Consumes: `prediction_type == "description"` (Task 1)

- [ ] **Step 1: Update `gui/selection_window.py`**

In `_SelectionRow.__init__`, after the line `self._trivial_radio = QRadioButton("Common Name")`, add:

```python
self._describe_radio = QRadioButton("Describe Image")
```

Then add it to the button group and layout alongside the others. The full radio-button block becomes:

```python
self._smiles_radio = QRadioButton("SMILES")
self._iupac_radio = QRadioButton("IUPAC Name")
self._trivial_radio = QRadioButton("Common Name")
self._describe_radio = QRadioButton("Describe Image")
self._type_group = QButtonGroup(self)
for btn in (self._smiles_radio, self._iupac_radio, self._trivial_radio, self._describe_radio):
    self._type_group.addButton(btn)
    layout.addWidget(btn)
self._smiles_radio.setChecked(True)
```

Update the `prediction_type` property to add one branch before the default `return "smiles"`:

```python
@property
def prediction_type(self) -> str:
    if self._iupac_radio.isChecked():
        return "iupac"
    if self._trivial_radio.isChecked():
        return "trivial"
    if self._describe_radio.isChecked():
        return "description"
    return "smiles"
```

- [ ] **Step 2: Update `gui/review_window.py`**

Change `_TYPE_LABELS` from:

```python
_TYPE_LABELS = {
    "iupac": "IUPAC Name:",
    "trivial": "Common Name:",
}
```

to:

```python
_TYPE_LABELS = {
    "iupac": "IUPAC Name:",
    "trivial": "Common Name:",
    "description": "Image Description:",
}
```

- [ ] **Step 3: Run full suite**

```bash
python -m pytest tests/ -v
```
Expected: all 60 pass

- [ ] **Step 4: Commit**

```bash
git add gui/selection_window.py gui/review_window.py
git commit -m "feat: add Describe Image option to SelectionWindow and ReviewWindow label"
```
