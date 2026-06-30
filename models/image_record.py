from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ImageRecord:
    id: str
    source_ref: str
    thumbnail_bytes: bytes
    recognition_bytes: bytes
    predicted_smiles: str | None = None
    confidence: float | None = None
    approved_value: str | None = None
    is_chemical: bool | None = None

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "approved_value": self.approved_value,
            "is_chemical": self.is_chemical,
        }

    @classmethod
    def from_review_dict(cls, d: dict) -> ImageRecord:
        return cls(
            id=d["id"],
            source_ref=d["source_ref"],
            thumbnail_bytes=b"",
            recognition_bytes=b"",
            predicted_smiles=d.get("predicted_smiles"),
            confidence=d.get("confidence"),
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
