# chem4all

A Python tool that makes chemistry course handouts and presentations accessible to visually impaired students.

chem4all processes PPTX and DOCX files, extracts images, identifies chemical structures using [DECIMER Image Transformer](https://github.com/Kohulan/DECIMER-Image_Transformer), and writes approved alt-text back to the original document. For each image the instructor can choose to produce a SMILES string, an IUPAC name, a common name, or a plain-English description — useful for non-chemical images like cell membranes and biochemical pathway diagrams.

## How it works

1. **Extract** — images are pulled from your PPTX or DOCX file and downscaled for processing
2. **Select** — choose which images to process and what kind of output to produce for each (SMILES, IUPAC name, common name, or image description)
3. **Recognize** — DECIMER identifies chemical structures; non-chemical images are described by GPT-4o vision via OpenRouter
4. **Review** — an instructor approves, edits, or overrides each prediction
5. **Write** — approved alt-text is written back to the document

## Requirements

- Python 3.9–3.12 — TensorFlow (required by DECIMER) does not publish wheels for Python 3.13+
- Homebrew (macOS only, source install only) — required for the `cairo` system library used for SVG support. Not needed if you download the packaged `.app` — cairo is bundled.
- An [OpenRouter](https://openrouter.ai) API key if you intend to use IUPAC name lookup, common name lookup, or image description (not needed for SMILES-only use)

## Installation

### Option A: Download the app (recommended for most users)

1. Download the `.dmg` for your Mac from the [latest release](../../releases/latest). Currently only Apple Silicon (`arm64`) Macs are supported — Intel and Windows builds are planned for a future release.
2. Open the `.dmg` and drag `chem4all.app` to your Applications folder.
3. Launch chem4all from Applications. No Python, Homebrew, or terminal setup is required — the app is self-contained except for the DECIMER model, which downloads automatically on first use.

### Option B: Run from source (for development)

#### 1. Clone the repository

```bash
git clone <repo-url>
cd chem4all
```

#### 2. Run the setup script

```bash
./setup.sh
```

The script installs all Python dependencies directly into the active interpreter using `pip install -e .`. No virtual environment is created or required.

#### 3. (Optional) Pre-download the DECIMER model

The DECIMER model (~500 MB) is downloaded on first use. To fetch it now so the GUI starts immediately:

```bash
python3 main.py --download-model
```

> **Note:** Ensure you have a stable internet connection and at least 2 GB of free disk space.

#### 4. (Optional) Configure your OpenRouter API key

Set the environment variable before launching, or enter the key in the GUI under **Settings**:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

The environment variable takes precedence over the value stored in settings.

## Usage

### GUI (recommended)

Launch the GUI with no arguments:

```bash
python main.py
# or, if installed as a package:
chem4all
```

**File picker** — click **Open File…** to select a `.pptx` or `.docx` file. While the document is being processed an extraction progress bar shows how many images have been found. If the DECIMER model was pre-downloaded, a load time is shown after startup.

**Select Images** — each extracted image is shown with a checkbox and four radio buttons:

| Option | What it produces |
|---|---|
| SMILES | The SMILES string of the chemical structure (DECIMER) |
| IUPAC Name | Human-readable IUPAC name derived from the SMILES (GPT-4o via OpenRouter) |
| Common Name | Everyday common name derived from the SMILES (GPT-4o via OpenRouter) |
| Describe Image | Single-sentence alt-text description for non-chemical images (GPT-4o vision via OpenRouter) |

Uncheck an image to exclude it from processing. Click **Start Identification** when ready.

**Review** — each image is shown with the predicted result and a custom override field. Leave the override blank to accept the prediction, or type your own value. Use **Previous / Next** to page through results (5 per page by default). Click **Accept & Finish** on the last page to write alt-text back to the document.

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
| `--download-model` | Pre-download the DECIMER model and exit |

> **Note:** The CLI path produces SMILES only. IUPAC name lookup, common name lookup, and image description are GUI features.

#### Examples

```bash
# Auto-accept all predictions and produce a new accessible file:
chem4all lecture.pptx

# Generate a review file for manual editing:
chem4all lecture.pptx --review

# Overwrite the original file:
chem4all handout.docx --in-place

# Specify an explicit output path:
chem4all lecture.pptx --output /shared/lecture_accessible.pptx
```

## Configuration

Settings are stored in `~/.chem4all/config.json` and created with defaults on first run. You can edit this file directly or use the **Settings** dialog in the GUI.

| Setting | Default | Description |
|---|---|---|
| `auto_filter` | `false` | Hide images below the confidence threshold before showing the review UI |
| `confidence_threshold` | `0.7` | Minimum DECIMER confidence score required when `auto_filter` is enabled |
| `thumbnail_max_size` | `256` | Maximum pixel dimension for thumbnails shown in the review UI |
| `recognition_max_size` | `1024` | Maximum pixel dimension of images sent to DECIMER |
| `output_mode` | `"new_file"` | `"new_file"` creates a new file; `"in_place"` overwrites the original |
| `page_size` | `5` | Number of images shown per page in the review UI |
| `openrouter_api_key` | `""` | OpenRouter API key (overridden by the `OPENROUTER_API_KEY` environment variable) |

## Running tests

```bash
pytest
```

## Project structure

```
chem4all/
├── main.py                  # Entry point (CLI + GUI launcher)
├── config.py                # Configuration loading and saving
├── setup.sh                 # Dependency installer
├── models/
│   └── image_record.py      # Shared ImageRecord dataclass
├── pipeline/
│   ├── extractor.py         # Extract images from PPTX/DOCX
│   ├── recognizer.py        # Run DECIMER on images
│   ├── namer.py             # IUPAC and common name lookup via OpenRouter
│   ├── describer.py         # Image description via GPT-4o vision
│   ├── reviewer.py          # CLI auto-accept and review file I/O
│   └── writer.py            # Write alt-text back to documents
├── gui/
│   ├── app.py               # PyQt6 application bootstrap
│   ├── splash.py            # Startup splash screen
│   ├── file_picker.py       # Initial file selection window
│   ├── selection_window.py  # Per-image type selection UI
│   ├── review_window.py     # Paged review UI
│   ├── settings_dialog.py   # Settings editor dialog
│   ├── worker.py            # Background QThread for recognition
│   ├── extractor_worker.py  # Background QThread for extraction
│   ├── model_manager.py     # DECIMER model download and preload
│   └── widgets.py           # Shared UI components (ThumbnailLabel)
└── tests/
```

## Known limitations

- **CLI is SMILES-only** — IUPAC name lookup, common name lookup, and image description are available in the GUI only.
- **DECIMER load time** — the TensorFlow model takes ~60–100 s to load on CPU. `tensorflow-metal` (Apple Silicon GPU acceleration) is not yet compatible with TensorFlow 2.16+ and Python 3.12, so CPU is the only supported backend.
- **DOCX image indexing** — images in DOCX files are indexed by relationship ID, which may not match visual reading order in complex layouts. PPTX support is more robust.
- **No review file apply** — the `--review` flag generates a JSON review file, but applying a previously-saved review back via CLI is not yet implemented.
