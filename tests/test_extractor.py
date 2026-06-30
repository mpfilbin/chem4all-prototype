from pathlib import Path
from PIL import Image
import io
import pytest
from config import Config
from pipeline.extractor import extract


def test_extract_pptx_returns_records(sample_pptx):
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_pptx, config)
    assert len(records) == 1
    r = records[0]
    assert r.id  # non-empty hash
    assert "slide 1" in r.source_ref.lower()
    assert r.thumbnail_bytes
    assert r.recognition_bytes
    assert r.predicted_smiles is None
    assert r.is_chemical is None


def test_extract_pptx_thumbnail_size(sample_pptx):
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_pptx, config)
    img = Image.open(io.BytesIO(records[0].thumbnail_bytes))
    assert max(img.size) <= 64


def test_extract_pptx_recognition_size(sample_pptx):
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_pptx, config)
    img = Image.open(io.BytesIO(records[0].recognition_bytes))
    assert max(img.size) <= 128


def test_extract_docx_returns_records(sample_docx):
    config = Config(thumbnail_max_size=64, recognition_max_size=128)
    records = extract(sample_docx, config)
    assert len(records) == 1
    r = records[0]
    assert r.id
    assert r.thumbnail_bytes
    assert r.recognition_bytes


def test_extract_unsupported_format_raises(tmp_path):
    bad = tmp_path / "file.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported"):
        extract(bad, Config())
