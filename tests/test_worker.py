from __future__ import annotations
import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from config import Config
from models.image_record import ImageRecord
from gui.worker import RecognizerWorker


def _make_record(prediction_type="smiles"):
    return ImageRecord(
        id="r1",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"fake_image",
        prediction_type=prediction_type,
    )


def test_worker_logs_recognizing_and_result(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record()], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Recognizing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> SMILES 'C1=CC=CC=C1'") for m in messages)


def test_worker_logs_iupac_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="iupac")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_logs_trivial_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", lambda smiles, api_key: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="trivial")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up common name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_logs_description(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_type="description")], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Describing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'A benzene ring diagram.'") for m in messages)
