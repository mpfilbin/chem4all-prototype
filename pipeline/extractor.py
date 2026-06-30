from __future__ import annotations
import hashlib
import io
import logging
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from docx import Document

from config import Config
from models.image_record import ImageRecord

log = logging.getLogger(__name__)


def extract(file_path: Path, config: Config) -> list[ImageRecord]:
    suffix = file_path.suffix.lower()
    if suffix == ".pptx":
        return _extract_pptx(file_path, config)
    elif suffix == ".docx":
        return _extract_docx(file_path, config)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def _downscale(raw_bytes: bytes, max_size: int) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_id(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _extract_pptx(file_path: Path, config: Config) -> list[ImageRecord]:
    prs = Presentation(str(file_path))
    records: list[ImageRecord] = []
    for slide_idx, slide in enumerate(prs.slides, start=1):
        for shape_idx, shape in enumerate(slide.shapes, start=1):
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            try:
                raw = shape.image.blob
                records.append(ImageRecord(
                    id=_make_id(raw),
                    source_ref=f"slide {slide_idx}, shape {shape_idx}",
                    thumbnail_bytes=_downscale(raw, config.thumbnail_max_size),
                    recognition_bytes=_downscale(raw, config.recognition_max_size),
                ))
            except (OSError, AttributeError, ValueError) as exc:
                log.warning("Could not extract image slide %d shape %d: %s", slide_idx, shape_idx, exc)
    return records


def _extract_docx(file_path: Path, config: Config) -> list[ImageRecord]:
    doc = Document(str(file_path))
    records: list[ImageRecord] = []
    image_idx = 0
    for para_idx, para in enumerate(doc.paragraphs, start=1):
        for run in para.runs:
            for rel in run.part.rels.values():
                if "image" in rel.reltype:
                    try:
                        raw = rel.target_part.blob
                        image_idx += 1
                        records.append(ImageRecord(
                            id=_make_id(raw),
                            source_ref=f"paragraph {para_idx}, image {image_idx}",
                            thumbnail_bytes=_downscale(raw, config.thumbnail_max_size),
                            recognition_bytes=_downscale(raw, config.recognition_max_size),
                        ))
                    except (OSError, AttributeError, ValueError) as exc:
                        log.warning("Could not extract image paragraph %d: %s", para_idx, exc)
    return records
