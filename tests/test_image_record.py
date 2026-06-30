import json
from models.image_record import ImageRecord


def test_image_record_defaults():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
    )
    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.approved_value is None
    assert record.is_chemical is None


def test_image_record_to_review_dict_excludes_bytes():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    assert "thumbnail_bytes" not in d
    assert "recognition_bytes" not in d
    assert d["id"] == "abc123"
    assert d["predicted_smiles"] == "C1=CC=CC=C1"
    assert d["approved_value"] == "C1=CC=CC=C1"
    assert d["is_chemical"] is True


def test_image_record_from_review_dict_roundtrip():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    restored = ImageRecord.from_review_dict(d)
    assert restored.id == record.id
    assert restored.approved_value == record.approved_value
    assert restored.thumbnail_bytes == b""
    assert restored.recognition_bytes == b""
