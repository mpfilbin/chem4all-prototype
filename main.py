from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


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
    args = parser.parse_args()

    from config import load_config, Config
    config = load_config(args.config)
    if args.in_place:
        config.output_mode = "in_place"

    if args.file is None:
        _launch_gui(config)
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


def _launch_gui(config) -> None:
    from PyQt6.QtWidgets import QApplication
    from gui.app import run_app
    import sys
    app = QApplication(sys.argv)
    run_app(app, config)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
