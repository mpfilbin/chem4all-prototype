from __future__ import annotations
import gzip
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from pipeline import name_dataset

log = logging.getLogger(__name__)

DATASET_URL = "https://<account>.blob.core.windows.net/chem4all/naming_dataset.sqlite.gz"


def _meta_path() -> Path:
    target = name_dataset.dataset_path()
    return target.with_suffix(target.suffix + ".meta")


def dataset_last_downloaded() -> datetime | None:
    meta = _meta_path()
    if not meta.exists():
        return None
    try:
        return datetime.fromisoformat(meta.read_text().splitlines()[0].strip())
    except (ValueError, IndexError):
        return None


class DatasetDownloadWorker(QThread):
    status = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # bytes_done, total_bytes
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            import requests
        except ImportError:
            self.error.emit("'requests' package not found — run: pip install requests")
            return

        target = name_dataset.dataset_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        self.status.emit("Downloading naming dataset…")
        try:
            self._download(requests, target)
        except Exception as exc:
            self.error.emit(f"Failed to download naming dataset: {exc}")
            return

        self.finished.emit()

    def _download(self, requests, target: Path) -> None:
        gz_path = target.with_suffix(target.suffix + ".gz.part")
        resp = requests.get(DATASET_URL, stream=True, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))

        downloaded = 0
        with open(gz_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)

        self.status.emit("Extracting naming dataset…")
        self.progress.emit(0, 0)  # switch to indeterminate during extraction
        tmp_sqlite = target.with_suffix(target.suffix + ".part")
        with gzip.open(gz_path, "rb") as src, open(tmp_sqlite, "wb") as dst:
            shutil.copyfileobj(src, dst)
        gz_path.unlink(missing_ok=True)
        tmp_sqlite.replace(target)  # atomic on the same filesystem

        _meta_path().write_text(f"{datetime.now(timezone.utc).isoformat()}\n{DATASET_URL}\n")
