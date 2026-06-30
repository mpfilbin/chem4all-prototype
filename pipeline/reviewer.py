from __future__ import annotations
import json
from pathlib import Path
from models.image_record import ImageRecord


def auto_accept(records: list[ImageRecord]) -> list[ImageRecord]:
    for record in records:
        if record.predicted_smiles is not None:
            record.approved_value = record.predicted_smiles
            record.is_chemical = True
    return records


def write_review_file(records: list[ImageRecord], path: Path) -> None:
    path.write_text(json.dumps([r.to_review_dict() for r in records], indent=2))


def load_review_file(path: Path) -> dict[str, ImageRecord]:
    data = json.loads(path.read_text())
    return {d["id"]: ImageRecord.from_review_dict(d) for d in data}
