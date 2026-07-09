# Design: Per-Stage Diagnostic Logging (Extraction, Recognition, OpenRouter, Write)

## Context

The diagnostic logging feature (see `2026-07-09-diagnostic-logging-design.md`) and the model-load logging that followed it only cover DECIMER model load timing. There is no visibility into the rest of the pipeline: opening a document, extracting each image, running DECIMER recognition per image, calling OpenRouter for IUPAC/trivial name lookup or image description, or writing the final accessible file. This adds per-image DEBUG-level tracing across all of those stages, so a diagnostic log file captures the full story of a run, not just the model load.

All new logging is DEBUG level, consistent with the existing setup: `pipeline.*`/`gui.*` loggers are only raised to DEBUG when diagnostic logging is enabled (`logging_setup.py`), so this is invisible on the console and in the log file until a user turns the feature on. Existing WARNING-level failure logging is untouched.

## Section 1 — Extraction (`pipeline/extractor.py`)

Both `_extract_pptx` and `_extract_docx` already compute a `total` image count and already have a `log` logger. Add:

- Right after `total` is computed: `log.debug("Opened %s (%d images found)", file_path.name, total)`
- Right after each `ImageRecord` is successfully appended (inside the existing `try` block, after `records.append(...)`): `log.debug("Extracted %s", records[-1].source_ref)`

This covers both CLI and GUI, since both call `pipeline.extractor.extract()` (GUI via `gui/extractor_worker.py`).

## Section 2 — DECIMER Recognition (two call sites)

DECIMER recognition happens via `_run_decimer` in `pipeline/recognizer.py`, but it's called from two independent places that don't share a code path: `recognize()` in the same file (CLI), and `RecognizerWorker.run()` in `gui/worker.py` (GUI, which calls `_run_decimer` directly, not through `recognize()`). `_run_decimer` itself doesn't know the image's `source_ref` — only the two callers do — so the per-image trace lines go in both callers, not inside `_run_decimer`.

**`pipeline/recognizer.py`'s `recognize()`** — around the existing `_run_decimer` call:

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

(`time` is already imported in this file from the model-load logging work.)

**`gui/worker.py`'s `RecognizerWorker.run()`** — same pattern around its own `_run_decimer` call, plus the same treatment for the OpenRouter calls (`lookup_iupac`, `lookup_trivial_name`, `describe_image` — GUI-only, the CLI never calls these, and their functions in `pipeline/namer.py`/`pipeline/describer.py` don't take a `source_ref` parameter and shouldn't gain one just for logging, since the caller here already has `record.source_ref` in scope). `gui/worker.py` needs `import time` added (not currently imported there). Full resulting `run()` method:

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

Each new debug line sits inside the `try` block that already surrounds its corresponding call, immediately before/after it — no new `try/except` blocks are introduced, only new lines inside existing ones.

## Section 3 — Write (`pipeline/writer.py`)

`_write_pptx` and `_write_docx` both already compute `approved` (the list of records actually being written) before saving. Add one line after each successful save, using the count already in scope:

```python
def _write_pptx(records: list[ImageRecord], dest: Path) -> None:
    approved = [r for r in records if r.is_chemical is True and r.approved_value]
    if not approved:
        return
    prs = Presentation(str(dest))
    for record in approved:
        ...
    prs.save(str(dest))
    log.debug("Wrote %s (%d alt-texts applied)", dest, len(approved))
```

Same pattern in `_write_docx` (`doc.save(str(dest))` followed by the same debug line). If `approved` is empty, both functions already return early before saving — no log line in that case, since nothing was actually written beyond the plain file copy `write()` already did.

## Testing

- `tests/test_extractor.py` — add assertions (via `caplog`) that opening a pptx/docx logs `"Opened ... (N images found)"` and each extracted image logs `"Extracted <source_ref>"`.
- `tests/test_recognizer.py` — add a `recognize()` test asserting `caplog` contains `"Recognizing <source_ref>..."` and a line starting with `"<source_ref> -> SMILES"`.
- `tests/test_writer.py` — add assertions that a successful write logs `"Wrote <dest> (<N> alt-texts applied)"`, and that a write with zero approved records does NOT log a "Wrote" line.
- `gui/worker.py`'s new logging (recognition + all three OpenRouter branches) is verified via a new `tests/test_worker.py` following the same offscreen-QThread pattern already established in `tests/test_model_manager.py` (instantiate `RecognizerWorker`, call `.run()` directly, fake `_run_decimer`/`lookup_iupac`/`lookup_trivial_name`/`describe_image`, assert on `caplog`).

```bash
python -m pytest tests/ -v
```
