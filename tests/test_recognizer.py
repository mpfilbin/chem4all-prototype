import pytest
from config import Config
from models.image_record import ImageRecord
from pipeline.recognizer import recognize


def _make_record(id="r1", recognition_bytes=b"fake_image"):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=recognition_bytes,
    )


def test_recognize_populates_smiles(monkeypatch):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C1=CC=CC=C1", 0.95),
    )
    records = [_make_record()]
    result = recognize(records, Config())
    assert result[0].predicted_smiles == "C1=CC=CC=C1"
    assert result[0].confidence == 0.95


def test_recognize_clears_recognition_bytes(monkeypatch):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C1=CC=CC=C1", 0.95),
    )
    records = [_make_record()]
    result = recognize(records, Config())
    assert result[0].recognition_bytes == b""


def test_recognize_handles_decimer_failure(monkeypatch):
    def fail(_):
        raise RuntimeError("DECIMER crashed")
    monkeypatch.setattr("pipeline.recognizer._run_decimer", fail)
    records = [_make_record()]
    result = recognize(records, Config())
    assert result[0].predicted_smiles is None
    assert result[0].recognition_bytes == b""


def test_recognize_autofilter_marks_low_confidence(monkeypatch):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C", 0.3),
    )
    config = Config(auto_filter=True, confidence_threshold=0.7)
    records = [_make_record()]
    result = recognize(records, config)
    assert result[0].is_chemical is False


def test_recognize_autofilter_keeps_high_confidence(monkeypatch):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C1=CC=CC=C1", 0.95),
    )
    config = Config(auto_filter=True, confidence_threshold=0.7)
    records = [_make_record()]
    result = recognize(records, config)
    assert result[0].is_chemical is not False
