from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ImageRecord:
    id: str
    source_ref: str
    thumbnail_bytes: bytes
    recognition_bytes: bytes
    predicted_smiles: str | None = None
    confidence: float | None = None
    iupac_name: str | None = None
    trivial_name: str | None = None
    description: str | None = None
    prediction_type: str = "smiles"
    approved_value: str | None = None
    is_chemical: bool | None = None

    def result_value(self) -> str | None:
        if self.prediction_type == "description":
            return self.description
        if self.prediction_type == "iupac":
            return self.iupac_name
        if self.prediction_type == "trivial":
            return self.trivial_name
        return self.predicted_smiles

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "iupac_name": self.iupac_name,
            "trivial_name": self.trivial_name,
            "description": self.description,
            "prediction_type": self.prediction_type,
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
            iupac_name=d.get("iupac_name"),
            trivial_name=d.get("trivial_name"),
            description=d.get("description"),
            prediction_type=d.get("prediction_type", "smiles"),
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
