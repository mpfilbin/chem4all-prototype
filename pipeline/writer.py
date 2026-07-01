from __future__ import annotations
import logging
import shutil
from pathlib import Path

from pptx import Presentation
from docx import Document

from config import Config
from models.image_record import ImageRecord

log = logging.getLogger(__name__)


def write(
    records: list[ImageRecord],
    source_path: Path,
    config: Config,
    output_path: Path | None = None,
) -> Path:
    if config.output_mode == "in_place" and output_path is None:
        dest = source_path
    elif output_path is not None:
        dest = output_path
    else:
        stem = source_path.stem
        dest = source_path.with_name(f"{stem}_accessible{source_path.suffix}")

    if dest != source_path:
        shutil.copy2(source_path, dest)

    suffix = source_path.suffix.lower()
    if suffix == ".pptx":
        _write_pptx(records, dest)
    elif suffix == ".docx":
        _write_docx(records, dest)
    return dest


def _parse_source_ref_pptx(source_ref: str) -> tuple[int, int]:
    # source_ref is 1-indexed; convert to 0-indexed
    parts = source_ref.replace(",", "").split()
    slide_idx = int(parts[1]) - 1
    shape_idx = int(parts[3]) - 1
    return slide_idx, shape_idx


def _write_pptx(records: list[ImageRecord], dest: Path) -> None:
    approved = [r for r in records if r.is_chemical is True and r.approved_value]
    if not approved:
        return
    prs = Presentation(str(dest))
    for record in approved:
        try:
            slide_idx, shape_idx = _parse_source_ref_pptx(record.source_ref)
            shape = list(prs.slides[slide_idx].shapes)[shape_idx]
            shape.element.nvPicPr.cNvPr.set("descr", record.approved_value)
        except Exception as exc:
            log.warning("Could not set alt-text for %s: %s", record.source_ref, exc)
    prs.save(str(dest))


def _write_docx(records: list[ImageRecord], dest: Path) -> None:
    approved = [r for r in records if r.is_chemical is True and r.approved_value]
    if not approved:
        return
    doc = Document(str(dest))
    # Build index of inline images by paragraph/image position
    img_index = 0
    ref_map: dict[str, object] = {}
    for para_idx, para in enumerate(doc.paragraphs, start=1):
        for run in para.runs:
            for rel in run.part.rels.values():
                if "image" in rel.reltype:
                    img_index += 1
                    ref_map[f"paragraph {para_idx}, image {img_index}"] = run.element
    for record in approved:
        elem = ref_map.get(record.source_ref)
        if elem is None:
            log.warning("No element found for %s", record.source_ref)
            continue
        try:
            # Set alt text via drawing element title attribute
            ns = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
            for drawing in elem.findall(f".//{{{ns}}}docPr"):
                drawing.set("descr", record.approved_value)
        except Exception as exc:
            log.warning("Could not set alt-text for %s: %s", record.source_ref, exc)
    doc.save(str(dest))
