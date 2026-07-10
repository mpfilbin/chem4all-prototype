from __future__ import annotations
from dataclasses import dataclass, field

_TYPE_ORDER = ["smiles", "iupac", "trivial", "description"]
_DECORATIVE_TEXT = "Decorative Image"


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
    prediction_types: list[str] = field(default_factory=lambda: ["decorative"])
    approved_value: str | None = None
    is_chemical: bool | None = None

    def result_lines(self) -> list[str]:
        # The Selection window enforces "decorative" as mutually exclusive
        # with the other four types, so prediction_types should never mix
        # them. This is a membership test (not equality) so a record that
        # somehow does mix them (e.g. hand-edited review JSON) still shows
        # the placeholder rather than a half-composed result — it degrades
        # gracefully instead of crashing, at the cost of the worker still
        # running (and discarding) any other requested lookups for it.
        if "decorative" in self.prediction_types:
            return [_DECORATIVE_TEXT]
        field_for_type = {
            "smiles": self.predicted_smiles,
            "iupac": self.iupac_name,
            "trivial": self.trivial_name,
            "description": self.description,
        }
        return [
            field_for_type[t]
            for t in _TYPE_ORDER
            if t in self.prediction_types and field_for_type[t]
        ]

    def to_review_dict(self) -> dict:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "predicted_smiles": self.predicted_smiles,
            "confidence": self.confidence,
            "iupac_name": self.iupac_name,
            "trivial_name": self.trivial_name,
            "description": self.description,
            "prediction_types": self.prediction_types,
            "approved_value": self.approved_value,
            "is_chemical": self.is_chemical,
        }

    @classmethod
    def from_review_dict(cls, d: dict) -> ImageRecord:
        prediction_types = d.get("prediction_types")
        if prediction_types is None:
            legacy_prediction_type = d.get("prediction_type")
            prediction_types = [legacy_prediction_type] if legacy_prediction_type else ["smiles"]
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
            prediction_types=prediction_types,
            approved_value=d.get("approved_value"),
            is_chemical=d.get("is_chemical"),
        )
