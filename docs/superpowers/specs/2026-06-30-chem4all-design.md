# chem4all — Design Spec

**Date:** 2026-06-30  
**Status:** Approved

## Overview

`chem4all` is a Python tool that makes chemistry course handouts and presentations accessible to visually impaired students. It processes PPTX and DOCX files, extracts images, runs chemical structure recognition via DECIMER Image Transformer, presents results to the instructor for review and approval, then writes approved SMILES strings (or instructor-provided overrides) back to the original document as alt-text.

---

## Goals

- Extract images from PPTX and DOCX files
- Identify chemical structures in those images using DECIMER
- Present a PyQt6 review UI for instructors to approve, edit, or reject predictions
- Write approved alt-text back to the source document (new file or in-place)
- Support both GUI (non-technical users) and CLI (batch processing) workflows
- Memory-efficient: never hold full-resolution image bytes beyond the extraction moment

**Out of scope (deferred):**
- SMILES → IUPAC name conversion
- Per-directory config overrides (home-dir config only for now)

---

## Architecture

Pipeline architecture (Approach B). Four independent stages share a common `ImageRecord` data model. CLI and GUI are both frontends over the same pipeline code. No stage reaches back into a previous one.

```
Input file
    │
    ▼
[Stage 1: Extractor]  →  list[ImageRecord] (thumbnails + recognition images)
    │
    ▼
[Stage 2: Recognizer]  →  ImageRecord.predicted_smiles populated; recognition_bytes cleared
    │
    ▼
[Stage 3: Reviewer]  →  ImageRecord.approved_value + is_chemical set
    │
    ▼
[Stage 4: Writer]  →  alt-text written to output file
```

---

## Project Structure

```
chem4all/
├── main.py                    # Entry point — CLI arg parsing; launches GUI or headless pipeline
├── config.py                  # Loads/saves ~/.chem4all/config.json
├── pipeline/
│   ├── extractor.py           # Stage 1: extract + downscale images from PPTX/DOCX
│   ├── recognizer.py          # Stage 2: run DECIMER; populate predictions
│   ├── reviewer.py            # Stage 3: CLI auto-accept or GUI review
│   └── writer.py              # Stage 4: write alt-text back to document
├── gui/
│   ├── app.py                 # PyQt6 application bootstrap
│   ├── file_picker.py         # Initial window: file open + Settings button
│   ├── settings_dialog.py     # Modal settings dialog
│   ├── review_window.py       # Paged review UI
│   └── worker.py              # QThread worker for off-thread DECIMER inference
├── models/
│   └── image_record.py        # ImageRecord dataclass
└── tests/
```

---

## Data Model

```python
@dataclass
class ImageRecord:
    id: str                      # SHA-256 hash of original image bytes
    source_ref: str              # e.g. "slide 3, shape 2" or "paragraph 7, image 1"
    thumbnail_bytes: bytes       # max thumbnail_max_size px on longest side (PNG)
    recognition_bytes: bytes     # max recognition_max_size px on longest side; cleared after Stage 2
    predicted_smiles: str | None # populated by Stage 2; None if DECIMER returned nothing
    confidence: float | None     # DECIMER confidence score, if available
    approved_value: str | None   # set by Stage 3: predicted_smiles or instructor override
    is_chemical: bool | None     # None = unreviewed; True = write alt-text; False = skip
```

`approved_value` is what gets written as alt-text. If the instructor accepts the prediction, `approved_value = predicted_smiles`. If they type an override, that value is used. If `is_chemical = False`, no alt-text is written for that image.

**Review file format:** JSON array of `ImageRecord` objects serialized without `recognition_bytes` or `thumbnail_bytes`, keyed by `id`. Used to re-apply a prior review session to a re-processed document.

---

## Pipeline Stages

### Stage 1 — Extractor (`pipeline/extractor.py`)

- Detects PPTX vs DOCX by file extension; delegates to `_extract_pptx` / `_extract_docx`
- For each image: extracts raw bytes → downscales to `thumbnail_bytes` and `recognition_bytes` via Pillow → computes `id` hash → records `source_ref` → yields `ImageRecord`
- Raw full-resolution bytes are never stored beyond this step
- Returns `list[ImageRecord]`

### Stage 2 — Recognizer (`pipeline/recognizer.py`)

Two modes (controlled by config):

- **Default (show-all):** DECIMER runs on all records in a `QThread` background worker. The review UI launches immediately and populates `predicted_smiles` fields as results arrive via `record_ready` signals. All images are shown to the instructor regardless of confidence — the instructor decides which are chemical structures.
- **Auto-filter mode:** DECIMER runs on all records before the review UI appears. The UI only launches after all inference is complete. Records below `confidence_threshold` get `is_chemical = False` and are excluded from the review UI. This mode is slower to reach the review step but reduces the number of images the instructor must manually assess.

After recognition (in either mode), `recognition_bytes` is cleared (`b""`) to free memory.

### Stage 3 — Reviewer (`pipeline/reviewer.py`)

Two modes:

- **CLI auto-accept:** Sets `approved_value = predicted_smiles` and `is_chemical = True` for every record with a non-None prediction. Records with no prediction are left as `is_chemical = None` (no alt-text written).
- **CLI with `--review` flag:** Serializes records to a JSON review file. Exits without write-back. A future run can pass this file as input to apply approved values.
- **GUI review:** Launches `review_window.py`. Returns the mutated record list on completion.

### Stage 4 — Writer (`pipeline/writer.py`)

- Iterates records where `is_chemical = True` and `approved_value` is set
- Uses `source_ref` to locate the correct shape (PPTX) or inline image (DOCX)
- Sets the alt-text attribute on that element
- **Output mode:**
  - Default: writes to a new file (e.g. `lecture_accessible.pptx`)
  - `--in-place` flag or `output_mode = "in_place"` config: overwrites the original

---

## GUI

### File Picker (`gui/file_picker.py`)

Initial window shown when no file is passed via CLI.

- "Open File..." button → `QFileDialog` filtered to `.pptx` / `.docx`
- "Settings" button → opens `SettingsDialog` modally
- Once a file is selected, file picker closes and the pipeline begins (recognizer in `QThread`, then review window)

### Settings Dialog (`gui/settings_dialog.py`)

Modal dialog. Controls:

| Setting | Widget |
|---|---|
| Auto-filter mode | Checkbox |
| Confidence threshold | Slider/spinbox (enabled only when auto-filter is on) |
| Thumbnail max size (px) | Spinbox |
| Recognition max size (px) | Spinbox |
| Output mode | Radio buttons (New file / In-place) |
| Review page size | Spinbox (5–10) |

Save button → writes `~/.chem4all/config.json`. Cancel discards changes.

### Worker (`gui/worker.py`)

`QThread` subclass running the recognizer stage. Signals:

- `progress(int, int)` — current index, total (drives progress bar)
- `record_ready(ImageRecord)` — emitted per record as inference completes
- `finished()`
- `error(str)`

### Review Window (`gui/review_window.py`)

Paged review UI. Each page shows `page_size` records (default 5, max 10).

Per-record row:
- Clickable thumbnail (`QLabel`) → opens full-size thumbnail in a modal dialog
- Source reference label (e.g. "Slide 3, Shape 2")
- Predicted SMILES (read-only `QLineEdit`)
- Override field (editable `QLineEdit`; empty = use predicted SMILES)
- "Not a chemical" checkbox → sets `is_chemical = False`, disables override field

Navigation bar: Previous / Next buttons + "Page X of Y" label

Bottom bar:
- **Cancel** — discards all approvals, closes window, no write-back
- **Accept** — finalizes current page; on the last page, triggers write-back

---

## Configuration

**Location:** `~/.chem4all/config.json` (created with defaults on first run)

```python
@dataclass
class Config:
    auto_filter: bool = False
    confidence_threshold: float = 0.7
    thumbnail_max_size: int = 256
    recognition_max_size: int = 1024
    output_mode: str = "new_file"   # "new_file" or "in_place"
    page_size: int = 5
```

Future: per-directory config files (`chem4all.json`) that override home-dir defaults.

---

## CLI Interface

```
chem4all [FILE] [OPTIONS]

Arguments:
  FILE                   Path to a .pptx or .docx file

Options:
  --review               Generate a JSON review file instead of auto-accepting
  --in-place             Overwrite the original file (default: produce new file)
  --output PATH          Explicit output file path
  --config PATH          Override config file location
```

If `FILE` is omitted, the PyQt6 GUI launches.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Image can't be extracted from a shape | Log warning, skip image, continue |
| DECIMER inference fails on one image | `predicted_smiles = None`, record still shown in review UI |
| Alt-text can't be set on a shape | Log warning, continue; report failures summary at end |
| Bad file path / unsupported format (CLI) | Print error, exit non-zero |
| Any error in GUI | Show `QMessageBox` dialog, do not crash |

---

## Testing

- **Unit:** Extractor (mock PPTX/DOCX with known images), Recognizer (mock DECIMER), Writer (assert alt-text set on correct shape)
- **Integration:** Small real PPTX fixture with one chemical structure image and one non-chemical image; run full pipeline end-to-end
- **GUI:** Not tested in initial version; pipeline is fully testable without Qt

---

## Dependencies

| Package | Purpose |
|---|---|
| `python-pptx` | PPTX parsing and alt-text write-back |
| `python-docx` | DOCX parsing and alt-text write-back |
| `DECIMER-Image_Transformer` | Chemical structure recognition |
| `Pillow` | Image downscaling |
| `PyQt6` | GUI framework |
