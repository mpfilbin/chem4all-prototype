import json
from pathlib import Path
from models.image_record import ImageRecord
from pipeline.reviewer import auto_accept, write_review_file, load_review_file


def _rec(id="r1", smiles=None):
    return ImageRecord(
        id=id, source_ref="slide 1, shape 1",
        thumbnail_bytes=b"", recognition_bytes=b"",
        predicted_smiles=smiles,
    )


def test_auto_accept_sets_approved_value():
    records = [_rec(smiles="C1=CC=CC=C1")]
    result = auto_accept(records)
    assert result[0].approved_value == "C1=CC=CC=C1"
    assert result[0].is_chemical is True


def test_auto_accept_skips_no_prediction():
    records = [_rec(smiles=None)]
    result = auto_accept(records)
    assert result[0].approved_value is None
    assert result[0].is_chemical is None


def test_write_and_load_review_file(tmp_path):
    records = [
        _rec("r1", "C1=CC=CC=C1"),
        _rec("r2", None),
    ]
    path = tmp_path / "review.json"
    write_review_file(records, path)
    data = json.loads(path.read_text())
    assert len(data) == 2
    loaded = load_review_file(path)
    assert "r1" in loaded
    assert loaded["r1"].predicted_smiles == "C1=CC=CC=C1"
    assert loaded["r1"].thumbnail_bytes == b""


def test_review_file_excludes_bytes(tmp_path):
    records = [_rec("r1", "C")]
    records[0].thumbnail_bytes = b"bigthumb"
    records[0].recognition_bytes = b"bigrecog"
    path = tmp_path / "review.json"
    write_review_file(records, path)
    raw = json.loads(path.read_text())
    assert "thumbnail_bytes" not in raw[0]
    assert "recognition_bytes" not in raw[0]
