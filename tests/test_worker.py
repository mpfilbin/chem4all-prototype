from __future__ import annotations
import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from config import Config
from models.image_record import ImageRecord
from gui.worker import RecognizerWorker


def _make_record(prediction_types=None):
    return ImageRecord(
        id="r1",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"fake_image",
        prediction_types=prediction_types or ["smiles"],
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
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key, image_bytes=None: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up IUPAC name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_passes_image_bytes_to_iupac_lookup(monkeypatch):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    calls = []
    monkeypatch.setattr(
        "pipeline.namer.lookup_iupac",
        lambda smiles, api_key, image_bytes=None: calls.append(image_bytes) or "benzene",
    )

    worker = RecognizerWorker([_make_record(prediction_types=["iupac"])], Config())
    worker.run()

    assert calls == [b"fake_image"]


def test_worker_logs_trivial_lookup(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_trivial_name", lambda smiles, api_key, image_bytes=None: "benzene")
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Looking up common name for slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'benzene'") for m in messages)


def test_worker_passes_image_bytes_to_trivial_lookup(monkeypatch):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    calls = []
    monkeypatch.setattr(
        "pipeline.namer.lookup_trivial_name",
        lambda smiles, api_key, image_bytes=None: calls.append(image_bytes) or "benzene",
    )

    worker = RecognizerWorker([_make_record(prediction_types=["trivial"])], Config())
    worker.run()

    assert calls == [b"fake_image"]


def test_worker_logs_description(monkeypatch, caplog):
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    worker = RecognizerWorker([_make_record(prediction_types=["description"])], Config())
    worker.run()

    messages = [r.message for r in caplog.records]
    assert "Describing slide 1, shape 1..." in messages
    assert any(m.startswith("slide 1, shape 1 -> 'A benzene ring diagram.'") for m in messages)


def test_worker_handles_multiple_prediction_types_in_one_record(monkeypatch, caplog):
    monkeypatch.setattr("gui.worker._run_decimer", lambda img_bytes: ("C1=CC=CC=C1", 0.95))
    monkeypatch.setattr("pipeline.namer.lookup_iupac", lambda smiles, api_key, image_bytes=None: "benzene")
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda img_bytes, api_key: "A benzene ring diagram.",
    )
    caplog.set_level(logging.DEBUG, logger="gui.worker")

    record = _make_record(prediction_types=["iupac", "description"])
    ready_records = []
    worker = RecognizerWorker([record], Config())
    worker.record_ready.connect(ready_records.append)
    worker.run()

    assert record.predicted_smiles == "C1=CC=CC=C1"
    assert record.iupac_name == "benzene"
    assert record.trivial_name is None
    assert record.description == "A benzene ring diagram."
    assert len(ready_records) == 1


def test_worker_does_not_process_decorative_record(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "gui.worker._run_decimer",
        lambda *args, **kwargs: calls.append("decimer") or ("C", 1.0),
    )
    monkeypatch.setattr(
        "pipeline.describer.describe_image",
        lambda *args, **kwargs: calls.append("describe") or "some description",
    )

    record = _make_record(prediction_types=["decorative"])
    ready_records = []
    worker = RecognizerWorker([record], Config())
    worker.record_ready.connect(ready_records.append)
    worker.run()

    assert calls == []
    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.iupac_name is None
    assert record.trivial_name is None
    assert record.description is None
    assert len(ready_records) == 1
    assert ready_records[0] is record


def test_worker_emits_status_for_decorative_record():
    record = _make_record(prediction_types=["decorative"])
    statuses = []
    worker = RecognizerWorker([record], Config())
    worker.status.connect(statuses.append)
    worker.run()

    assert len(statuses) == 1
    assert "slide 1, shape 1" in statuses[0]
