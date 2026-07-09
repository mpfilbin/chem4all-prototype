import logging
import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pipeline.recognizer as recognizer_module
from gui.model_manager import ModelPreloadWorker


@pytest.fixture(autouse=True)
def _reset_decimer_loaded_flag(monkeypatch):
    monkeypatch.setattr(recognizer_module, "_decimer_loaded", False)


def _fake_decimer_module(predict_SMILES):
    return types.SimpleNamespace(predict_SMILES=predict_SMILES)


def test_model_preload_worker_logs_load_start_and_duration(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "DECIMER", _fake_decimer_module(lambda img: "C"))
    caplog.set_level(logging.DEBUG, logger="gui.model_manager")

    results = []
    worker = ModelPreloadWorker()
    worker.finished.connect(lambda elapsed: results.append(("finished", elapsed)))
    worker.error.connect(lambda msg: results.append(("error", msg)))
    worker.run()

    assert results[0][0] == "finished"
    assert isinstance(results[0][1], float)
    messages = [r.message for r in caplog.records]
    assert "Loading DECIMER model..." in messages
    assert any(m.startswith("DECIMER model loaded in") for m in messages)
    assert recognizer_module._decimer_loaded is True


def test_model_preload_worker_logs_warning_on_failure(monkeypatch, caplog):
    def _boom(img):
        raise RuntimeError("model file missing")

    monkeypatch.setitem(sys.modules, "DECIMER", _fake_decimer_module(_boom))
    caplog.set_level(logging.DEBUG, logger="gui.model_manager")

    results = []
    worker = ModelPreloadWorker()
    worker.finished.connect(lambda elapsed: results.append(("finished", elapsed)))
    worker.error.connect(lambda msg: results.append(("error", msg)))
    worker.run()

    assert results[0] == ("error", "model file missing")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("DECIMER model failed to load" in r.message for r in warnings)
    assert recognizer_module._decimer_loaded is False
