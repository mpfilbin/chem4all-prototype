from __future__ import annotations
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone
from pipeline import name_dataset
from gui import dataset_manager


def test_dataset_last_downloaded_returns_none_when_no_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    assert dataset_manager.dataset_last_downloaded() is None


def test_dataset_last_downloaded_parses_sidecar_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    ts = datetime(2026, 8, 12, 9, 30, tzinfo=timezone.utc)
    (tmp_path / "names.sqlite.meta").write_text(f"{ts.isoformat()}\nhttps://example/foo.gz\n")
    assert dataset_manager.dataset_last_downloaded() == ts


def test_dataset_last_downloaded_returns_none_on_corrupt_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    (tmp_path / "names.sqlite.meta").write_text("not-a-timestamp\n")
    assert dataset_manager.dataset_last_downloaded() is None
