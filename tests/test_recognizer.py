import logging
import sys
import types
import pytest
from config import Config
from models.image_record import ImageRecord
import pipeline.recognizer as recognizer_module
from pipeline.recognizer import recognize, _run_decimer


def _make_record(id="r1", recognition_bytes=b"fake_image"):
    return ImageRecord(
        id=id,
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=recognition_bytes,
    )


def _fake_decimer_module(predict_SMILES):
    return types.SimpleNamespace(predict_SMILES=predict_SMILES)


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



def test_recognize_empty_list(monkeypatch):
    monkeypatch.setattr("pipeline.recognizer._run_decimer", lambda _: ("C", 1.0))
    assert recognize([], Config()) == []


def test_run_decimer_logs_model_load_start_and_duration_on_first_call(monkeypatch, caplog, red_png_bytes):
    monkeypatch.setattr(recognizer_module, "_decimer_loaded", False)
    monkeypatch.setitem(sys.modules, "DECIMER", _fake_decimer_module(lambda img: "C1=CC=CC=C1"))
    caplog.set_level(logging.DEBUG, logger="pipeline.recognizer")

    _run_decimer(red_png_bytes)

    messages = [r.message for r in caplog.records]
    assert "Loading DECIMER model..." in messages
    assert any(m.startswith("DECIMER model loaded in") for m in messages)
    assert recognizer_module._decimer_loaded is True


def test_run_decimer_skips_load_logging_when_already_loaded(monkeypatch, caplog, red_png_bytes):
    monkeypatch.setattr(recognizer_module, "_decimer_loaded", True)
    monkeypatch.setitem(sys.modules, "DECIMER", _fake_decimer_module(lambda img: "C1=CC=CC=C1"))
    caplog.set_level(logging.DEBUG, logger="pipeline.recognizer")

    _run_decimer(red_png_bytes)

    messages = [r.message for r in caplog.records]
    assert "Loading DECIMER model..." not in messages
    assert not any(m.startswith("DECIMER model loaded in") for m in messages)


def test_run_decimer_logs_warning_on_load_failure(monkeypatch, caplog, red_png_bytes):
    monkeypatch.setattr(recognizer_module, "_decimer_loaded", False)

    def _boom(img):
        raise RuntimeError("model file missing")

    monkeypatch.setitem(sys.modules, "DECIMER", _fake_decimer_module(_boom))
    caplog.set_level(logging.DEBUG, logger="pipeline.recognizer")

    with pytest.raises(RuntimeError, match="model file missing"):
        _run_decimer(red_png_bytes)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("DECIMER model failed to load" in r.message for r in warnings)
    assert recognizer_module._decimer_loaded is False


def test_recognize_logs_recognizing_and_result(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.recognizer._run_decimer",
        lambda img_bytes: ("C1=CC=CC=C1", 0.95),
    )
    caplog.set_level(logging.DEBUG, logger="pipeline.recognizer")
    records = [_make_record()]
    recognize(records, Config())
    messages = [r.message for r in caplog.records]
    assert "Recognizing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> SMILES 'C1=CC=CC=C1'") for m in messages)
