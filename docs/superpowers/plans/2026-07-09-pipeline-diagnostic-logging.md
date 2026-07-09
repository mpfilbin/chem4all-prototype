# Per-Stage Diagnostic Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-image DEBUG-level diagnostic logging across document extraction, DECIMER recognition (both CLI and GUI call sites), OpenRouter calls (IUPAC/trivial name lookup, image description), and the final file write — extending the existing diagnostic logging feature beyond just DECIMER model load timing.

**Architecture:** No new modules. Each pipeline stage's existing logger (`pipeline.extractor`, `pipeline.recognizer`, `gui.worker`, `pipeline.writer` — all already `logging.getLogger(__name__)`) gets new `log.debug(...)` calls wrapped around its existing per-image work, inside the try/except blocks that already exist. No new try/except blocks, no new config, no new UI.

**Tech Stack:** Python stdlib `logging`, pytest (`caplog` fixture) — existing project stack, no new dependencies.

## Global Constraints

- All new logging is DEBUG level — never INFO or higher, since `pipeline.*`/`gui.*` loggers are only raised to DEBUG when diagnostic logging is enabled (`logging_setup.py`'s `_DIAGNOSTIC_LOGGER_NAMES`); an INFO-level line would leak to the console even with the feature off.
- Existing WARNING-level failure logging is untouched — do not change any existing `log.warning(...)` call.
- No new `try/except` blocks — every new debug line goes inside a `try` block that already exists around the call it's describing.
- `namer.py`/`describer.py` function signatures (`lookup_iupac`, `lookup_trivial_name`, `describe_image`) do not change — no `source_ref` parameter added to them. Logging that needs `source_ref` goes at the call site in `gui/worker.py`, which already has it in scope.
- `_run_decimer`'s signature does not change — per-image logging goes at its two call sites (`pipeline/recognizer.py`'s `recognize()` and `gui/worker.py`'s `RecognizerWorker.run()`), not inside `_run_decimer` itself.

Reference spec: `docs/superpowers/specs/2026-07-09-pipeline-diagnostic-logging-design.md`

---

### Task 1: Extraction logging (`pipeline/extractor.py`)

**Files:**
- Modify: `pipeline/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- No new functions or signatures — `extract()`, `_extract_pptx()`, `_extract_docx()` keep their existing signatures.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_extractor.py` (add `import logging` near the top with the other imports):

```python
def test_extract_pptx_logs_opened_and_extracted(sample_pptx, caplog):
    caplog.set_level(logging.DEBUG, logger="pipeline.extractor")
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_pptx, config)
    messages = [r.message for r in caplog.records]
    assert any(m.startswith("Opened") and "1 images found" in m for m in messages)
    assert f"Extracted {records[0].source_ref}" in messages


def test_extract_docx_logs_opened_and_extracted(sample_docx, caplog):
    caplog.set_level(logging.DEBUG, logger="pipeline.extractor")
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_docx, config)
    messages = [r.message for r in caplog.records]
    assert any(m.startswith("Opened") and "1 images found" in m for m in messages)
    assert f"Extracted {records[0].source_ref}" in messages
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extractor.py -v -k logs`
Expected: FAIL — `assert any(...)` is `False` (no such log lines exist yet)

- [ ] **Step 3: Implement the logging**

In `pipeline/extractor.py`'s `_extract_pptx`, right after `total` is computed:

```python
    total = sum(
        1 for slide in prs.slides
        for shape in slide.shapes
        if _is_picture_shape(shape)
    )
    log.debug("Opened %s (%d images found)", file_path.name, total)
    records: list[ImageRecord] = []
```

And right after `records.append(...)` inside the existing `try` block (still inside the `try`, after the append):

```python
            try:
                raw = shape.image.blob
                records.append(ImageRecord(
                    id=_make_id(raw),
                    source_ref=f"slide {slide_idx}, shape {shape_idx}",
                    thumbnail_bytes=_downscale(raw, config.thumbnail_max_size),
                    recognition_bytes=_downscale(raw, config.recognition_max_size),
                ))
                log.debug("Extracted %s", records[-1].source_ref)
            except (OSError, AttributeError, ValueError) as exc:
```

In `_extract_docx`, right after `total = len(image_rids)`:

```python
    total = len(image_rids)
    log.debug("Opened %s (%d images found)", file_path.name, total)
    records: list[ImageRecord] = []
```

And right after `records.append(...)` inside its existing `try` block:

```python
        try:
            raw = rel.target_part.blob
            image_idx += 1
            records.append(ImageRecord(
                id=_make_id(raw),
                source_ref=f"image {image_idx}",
                thumbnail_bytes=_downscale(raw, config.thumbnail_max_size),
                recognition_bytes=_downscale(raw, config.recognition_max_size),
            ))
            log.debug("Extracted %s", records[-1].source_ref)
        except (OSError, AttributeError, ValueError) as exc:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extractor.py -v`
Expected: PASS (all tests in the file, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add pipeline/extractor.py tests/test_extractor.py
git commit -m "feat: log document open and per-image extraction at DEBUG level"
```

---

### Task 2: CLI recognition logging (`pipeline/recognizer.py`)

**Files:**
- Modify: `pipeline/recognizer.py`
- Test: `tests/test_recognizer.py`

**Interfaces:**
- No new functions or signatures — `recognize()` and `_run_decimer()` keep their existing signatures. `time` is already imported in this file (from the earlier model-load logging work).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_recognizer.py` (this file already has `import logging` from the model-load logging tests):

```python
def test_recognize_logs_recognizing_and_result(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C1=CC=CC=C1", 0.95),
    )
    caplog.set_level(logging.DEBUG, logger="pipeline.recognizer")
    records = [_make_record()]
    recognize(records, Config())
    messages = [r.message for r in caplog.records]
    assert "Recognizing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> SMILES 'C1=CC=CC=C1'") for m in messages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognizer.py -v -k recognizing_and_result`
Expected: FAIL — `assert "Recognizing slide 1, shape 1..." in messages` is `False`

- [ ] **Step 3: Implement the logging**

In `pipeline/recognizer.py`, change `recognize()`:

```python
def recognize(records: list[ImageRecord], config: Config) -> list[ImageRecord]:
    for record in records:
        try:
            log.debug("Recognizing %s...", record.source_ref)
            t0 = time.perf_counter()
            smiles, confidence = _run_decimer(record.recognition_bytes)
            log.debug("%s -> SMILES '%s' (%.2fs)", record.source_ref, smiles, time.perf_counter() - t0)
            record.predicted_smiles = smiles
            record.confidence = confidence
        except Exception as exc:
            log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
            record.predicted_smiles = None
            record.confidence = None
        finally:
            record.recognition_bytes = b""
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_recognizer.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Commit**

```bash
git add pipeline/recognizer.py tests/test_recognizer.py
git commit -m "feat: log per-image DECIMER recognition timing in CLI pipeline"
```

---

### Task 3: GUI worker logging (`gui/worker.py`)

**Files:**
- Modify: `gui/worker.py`
- Test: `tests/test_worker.py` (new file)

**Interfaces:**
- No new functions or signatures — `RecognizerWorker.run()` keeps its existing behavior and signals. `gui/worker.py` needs `import time` added (not currently imported there).
- Consumes: `ImageRecord` (from `models/image_record.py`, has a `prediction_type: str = "smiles"` field with valid values `"smiles"`, `"iupac"`, `"trivial"`, `"description"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_worker.py`:

```python
from __future__ import annotations
import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from config import Config
from models.image_record import ImageRecord
from gui.worker import RecognizerWorker


def _make_record(prediction_type="smiles"):
    return ImageRecord(
        id="r1",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"fake_image",
        prediction_type=prediction_type,
    )


def test_worker_logs_recognizing_and_result(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record()], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Recognizing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> SMILES 'C1=CC=CC=C1'") for m in messages)


def test_worker_logs_iupac_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="iupac")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_logs_trivial_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="trivial")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up common name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_logs_description(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="description")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Describing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'A benzene ring diagram.'") for m in messages)
```

Note: `gui/worker.py`'s `run()` imports `_run_decimer` at module load time (`from pipeline.recognizer import _run_decimer` at the top of the file), so patch target is `gui.worker._run_decimer` — but it imports `lookup_iupac`/`lookup_trivial_name`/`describe_image` freshly inside `run()` each call (`from pipeline.namer import ...` / `from pipeline.describer import ...` inside the method body), so those patch targets are the source modules (`pipeline.namer.lookup_iupac`, etc.), re-resolved at call time. This mirrors the existing pattern in `tests/test_main.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`
Expected: FAIL — all 4 tests fail on the `assert ... in messages` lines (no such log lines exist yet)

- [ ] **Step 3: Implement the logging**

In `gui/worker.py`, add `import time` under the existing `import os` line, and change `run()` to:

```python
    def run(self) -> None:
        from pipeline.describer import describe_image
        from pipeline.namer import lookup_iupac, lookup_trivial_name
        api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
        total = len(self._records)
        for i, record in enumerate(self._records):

            if record.prediction_type == "description":
                self.status.emit(f"Describing {record.source_ref}  ({i + 1} of {total})…")
                try:
                    log.debug("Describing %s...", record.source_ref)
                    t0 = time.perf_counter()
                    record.description = describe_image(record.recognition_bytes, api_key)
                    log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.description, time.perf_counter() - t0)
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
                log.debug("Recognizing %s...", record.source_ref)
                t0 = time.perf_counter()
                smiles, confidence = _run_decimer(record.recognition_bytes)
                log.debug("%s -> SMILES '%s' (%.2fs)", record.source_ref, smiles, time.perf_counter() - t0)
                record.predicted_smiles = smiles
                record.confidence = confidence

                if record.prediction_type == "iupac" and smiles:
                    self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                    try:
                        log.debug("Looking up IUPAC name for %s...", record.source_ref)
                        t0 = time.perf_counter()
                        record.iupac_name = lookup_iupac(smiles, api_key)
                        log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.iupac_name, time.perf_counter() - t0)
                    except Exception as exc:
                        log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                elif record.prediction_type == "trivial" and smiles:
                    self.status.emit(f"Looking up common name for {record.source_ref}…")
                    try:
                        log.debug("Looking up common name for %s...", record.source_ref)
                        t0 = time.perf_counter()
                        record.trivial_name = lookup_trivial_name(smiles, api_key)
                        log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.trivial_name, time.perf_counter() - t0)
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker.py -v`
Expected: PASS (all 4 new tests)

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add gui/worker.py tests/test_worker.py
git commit -m "feat: log per-image recognition and OpenRouter calls in GUI worker"
```

---

### Task 4: Write logging (`pipeline/writer.py`)

**Files:**
- Modify: `pipeline/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- No new functions or signatures — `write()`, `_write_pptx()`, `_write_docx()` keep their existing signatures.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_writer.py` (add `import logging` near the top with the other imports):

```python
def test_writer_pptx_logs_wrote(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="pipeline.writer")
    src = _make_pptx_with_image(tmp_path)
    record = _approved_record("slide 1, shape 1")
    out = write([record], src, Config(output_mode="new_file"))
    messages = [r.message for r in caplog.records]
    assert any(m.startswith(f"Wrote {out}") and "1 alt-texts applied" in m for m in messages)


def test_writer_pptx_no_wrote_log_when_nothing_approved(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="pipeline.writer")
    src = _make_pptx_with_image(tmp_path)
    record = ImageRecord(
        id="abc", source_ref="slide 1, shape 1",
        thumbnail_bytes=b"", recognition_bytes=b"",
        is_chemical=False,
    )
    write([record], src, Config(output_mode="new_file"))
    messages = [r.message for r in caplog.records]
    assert not any(m.startswith("Wrote") for m in messages)


def test_writer_docx_logs_wrote(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="pipeline.writer")
    src = _make_docx_with_image(tmp_path)
    out = write([_approved_record("image 1")], src, Config(output_mode="new_file"))
    messages = [r.message for r in caplog.records]
    assert any(m.startswith(f"Wrote {out}") and "1 alt-texts applied" in m for m in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_writer.py -v -k logs_wrote`
Expected: FAIL — `assert any(...)` is `False` (no such log lines exist yet)

- [ ] **Step 3: Implement the logging**

In `pipeline/writer.py`'s `_write_pptx`, right after `prs.save(str(dest))`:

```python
    prs.save(str(dest))
    log.debug("Wrote %s (%d alt-texts applied)", dest, len(approved))
```

In `_write_docx`, right after `doc.save(str(dest))`:

```python
    doc.save(str(dest))
    log.debug("Wrote %s (%d alt-texts applied)", dest, len(approved))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_writer.py -v`
Expected: PASS (all tests in the file, including the 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add pipeline/writer.py tests/test_writer.py
git commit -m "feat: log file write with alt-text count at DEBUG level"
```

---

### Task 5: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full automated test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests, including everything added in Tasks 1-4)

- [ ] **Step 2: CLI smoke test with diagnostic logging enabled**

Using a scratch config (do not touch `~/.chem4all/config.json`):

```bash
python3 -c "
from config import Config, save_config
c = Config(diagnostic_logging_enabled=True, diagnostic_log_dir='/tmp/chem4all-smoke/logs')
save_config(c, '/tmp/chem4all-smoke/config.json')
"
python3 main.py --config /tmp/chem4all-smoke/config.json --review path/to/sample.pptx
cat /tmp/chem4all-smoke/logs/chem4all-*.log
```

Expected: the log file contains, in order, an `"Opened ... (N images found)"` line, an `"Extracted ..."` line per image, a `"Recognizing ..."` / `"... -> SMILES ..."` pair per image, and no `"Wrote ..."` line (the `--review` path writes a `.review.json` file, not the accessible document, so `pipeline/writer.py` is never invoked in this flow — confirm this is expected by checking `main.py`'s `--review` branch, not a bug).

- [ ] **Step 3: CLI smoke test through the full write path**

```bash
python3 main.py --config /tmp/chem4all-smoke/config.json path/to/sample.pptx
cat /tmp/chem4all-smoke/logs/chem4all-*.log
```

Expected: this run's log file additionally contains a `"Wrote ... alt-texts applied"` line (this CLI path calls `auto_accept()` then `write()`, unlike `--review` which stops before writing).

- [ ] **Step 4: Clean up scratch files**

```bash
rm -rf /tmp/chem4all-smoke
```
