from __future__ import annotations
import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chem4all",
        description="Make chemistry documents accessible to visually impaired students.",
    )
    parser.add_argument("file", nargs="?", type=Path, help="Path to .pptx or .docx file")
    parser.add_argument("--review", action="store_true", help="Generate review file instead of auto-accepting")
    parser.add_argument("--in-place", action="store_true", dest="in_place", help="Overwrite original file")
    parser.add_argument("--output", type=Path, help="Explicit output file path")
    parser.add_argument("--config", type=Path, help="Override config file location")
    parser.add_argument("--download-model", action="store_true", help="Pre-download the DECIMER model and exit")
    args = parser.parse_args()

    if args.download_model:
        print("Downloading DECIMER model (this may take several minutes)...")
        import DECIMER.decimer  # noqa: F401 — triggers pystow download
        print("Model ready.")
        return

    from config import load_config
    config = load_config(args.config)
    from logging_setup import configure_logging
    configure_logging(config)
    if args.in_place:
        config.output_mode = "in_place"

    if args.file is None:
        _launch_gui(config, args.config)
        return

    file_path = args.file
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    if file_path.suffix.lower() not in (".pptx", ".docx"):
        print(f"Error: unsupported file format: {file_path.suffix}", file=sys.stderr)
        sys.exit(1)

    from pipeline.extractor import extract
    from pipeline.recognizer import recognize
    from pipeline.reviewer import auto_accept, write_review_file
    from pipeline.writer import write

    records = extract(file_path, config)
    records = recognize(records, config)

    if args.review:
        review_path = file_path.with_suffix(".review.json")
        write_review_file(records, review_path)
        print(f"Review file written to {review_path}")
        return

    records = auto_accept(records)
    out = write(records, file_path, config, args.output)
    print(f"Accessible file written to {out}")


def _launch_gui(config, config_path: Path | None = None) -> None:
    from PyQt6.QtWidgets import QApplication
    from gui.app import run_app
    app = QApplication(sys.argv)
    _window = run_app(config, config_path)  # noqa: F841 — keeps window alive during event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
