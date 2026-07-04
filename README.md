# chem4all

A Python tool that makes chemistry course handouts and presentations accessible to visually impaired students.

chem4all processes PPTX and DOCX files, extracts images, identifies chemical structures using [DECIMER Image Transformer](https://github.com/Kohulan/DECIMER-Image_Transformer), and writes approved SMILES strings as alt-text back to the original document.

## How it works

1. **Extract** — images are pulled from your PPTX or DOCX file and downscaled for processing
2. **Recognize** — DECIMER identifies chemical structures and predicts their SMILES representation
3. **Review** — an instructor approves, edits, or rejects each prediction
4. **Write** — approved SMILES strings are written back to the document as alt-text

## Requirements

- Python 3.11 or 3.12 — TensorFlow (required by DECIMER) does not yet publish wheels for Python 3.13+
- DECIMER Image Transformer (installed by `setup.sh`)

## Installation

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd chem4all
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Run the setup script

```bash
./setup.sh
```

The script installs TensorFlow and all other dependencies automatically. On Apple Silicon it also installs `tensorflow-metal` for GPU acceleration.

When it finishes, activate the virtual environment:

```bash
source venv/bin/activate
```

> **Note:** DECIMER downloads a large model on first run. Ensure you have a stable internet connection and at least 2 GB of free disk space.

## Usage

### GUI (recommended for non-technical users)

Launch the GUI by running `chem4all` with no arguments:

```bash
chem4all
# or
python main.py
```

A file picker window will open. From here you can:

- Click **Open File…** to select a `.pptx` or `.docx` file
- Click **Settings** to configure processing options before you begin

Once a file is selected, DECIMER runs in the background while the review screen loads. Each image is shown with:

- A clickable thumbnail (click to enlarge)
- The predicted SMILES string (read-only)
- An override field — leave blank to accept the prediction, or type your own value
- A "Not a chemical structure" checkbox to exclude the image from alt-text

Use **Previous / Next** to page through results (5 images per page by default). Click **Accept & Finish** on the last page to write alt-text back to the document.

### CLI

```
chem4all [FILE] [OPTIONS]
```

| Argument | Description |
|---|---|
| `FILE` | Path to a `.pptx` or `.docx` file |
| `--review` | Write a JSON review file instead of auto-accepting predictions |
| `--in-place` | Overwrite the original file (default: creates `filename_accessible.pptx`) |
| `--output PATH` | Explicit output file path |
| `--config PATH` | Use a custom config file instead of `~/.chem4all/config.json` |

#### Examples

**Auto-accept all predictions and produce a new accessible file:**

```bash
chem4all lecture.pptx
# output: lecture_accessible.pptx
```

**Generate a review file for manual editing, then apply it later:**

```bash
chem4all lecture.pptx --review
# output: lecture.review.json
```

**Overwrite the original file:**

```bash
chem4all handout.docx --in-place
```

**Specify an explicit output path:**

```bash
chem4all lecture.pptx --output /shared/lecture_accessible.pptx
```

## Configuration

Settings are stored in `~/.chem4all/config.json` and created with defaults on first run. You can edit this file directly or use the Settings dialog in the GUI.

| Setting | Default | Description |
|---|---|---|
| `auto_filter` | `false` | Run DECIMER on all images before showing the review UI, hiding images below the confidence threshold. Slower to reach review but reduces manual work for large presentations. |
| `confidence_threshold` | `0.7` | Minimum DECIMER confidence score required to show an image when `auto_filter` is enabled |
| `thumbnail_max_size` | `256` | Maximum pixel dimension for thumbnails shown in the review UI |
| `recognition_max_size` | `1024` | Maximum pixel dimension of images sent to DECIMER |
| `output_mode` | `"new_file"` | `"new_file"` creates a new accessible file; `"in_place"` overwrites the original |
| `page_size` | `5` | Number of images shown per page in the review UI (5–10) |

## Running tests

```bash
source venv/bin/activate
pytest
```

## Project structure

```
chem4all/
├── main.py               # Entry point (CLI + GUI launcher)
├── config.py             # Configuration loading and saving
├── models/
│   └── image_record.py   # Shared ImageRecord dataclass
├── pipeline/
│   ├── extractor.py      # Extract images from PPTX/DOCX
│   ├── recognizer.py     # Run DECIMER on images
│   ├── reviewer.py       # CLI auto-accept and review file I/O
│   └── writer.py         # Write alt-text back to documents
├── gui/
│   ├── app.py            # PyQt6 application bootstrap
│   ├── file_picker.py    # Initial file selection window
│   ├── settings_dialog.py # Settings editor dialog
│   ├── review_window.py  # Paged review UI
│   └── worker.py         # Background QThread for DECIMER inference
└── tests/
```

## Known limitations (v0.1)

- **SMILES only** — alt-text is written as a SMILES string. IUPAC name conversion is planned for a future release.
- **DOCX support** — images in DOCX files are supported but complex layouts with multiple images per paragraph may produce unexpected indexing. PPTX support is more robust.
- **No review file apply** — the `--review` flag generates a JSON review file, but applying a previously-saved review file via CLI is not yet implemented.
