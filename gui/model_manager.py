from __future__ import annotations
import logging
import zipfile
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

MODEL_URLS: dict[str, str] = {
    "DECIMER": "https://zenodo.org/record/8300489/files/models.zip",
    "DECIMER_HandDrawn": "https://zenodo.org/records/10781330/files/DECIMER_HandDrawn_model.zip",
}


def _decimer_home() -> Path | None:
    try:
        import pystow
        return Path(pystow.join("DECIMER-V2"))
    except ImportError:
        return None


def is_model_ready() -> bool:
    home = _decimer_home()
    if home is None:
        return False
    return all(
        (home / f"{name}_model" / "saved_model.pb").exists()
        for name in MODEL_URLS
    )


class ModelPreloadWorker(QThread):
    """Imports DECIMER in the background so the TF model is warm before first use."""
    finished = pyqtSignal(float)  # elapsed_seconds
    error = pyqtSignal(str)

    def run(self) -> None:
        import time
        from pipeline.recognizer import mark_decimer_loaded
        log.debug("Loading DECIMER model...")
        t0 = time.perf_counter()
        try:
            import numpy as np
            from DECIMER import predict_SMILES
            # Warm-up: force TF graph tracing now so the first real prediction is instant.
            predict_SMILES(np.zeros((64, 64, 3), dtype=np.uint8))
            elapsed = time.perf_counter() - t0
            log.debug("DECIMER model loaded in %.2fs", elapsed)
            mark_decimer_loaded()
            self.finished.emit(elapsed)
        except Exception as exc:
            log.warning("DECIMER model failed to load: %s", exc)
            self.error.emit(str(exc))


class ModelDownloadWorker(QThread):
    status = pyqtSignal(str)       # step description
    progress = pyqtSignal(int, int)  # bytes_done, total_bytes
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            import requests
        except ImportError:
            self.error.emit("'requests' package not found — run: pip install requests")
            return

        home = _decimer_home()
        if home is None:
            self.error.emit("pystow not installed — run setup.sh first")
            return

        home.mkdir(parents=True, exist_ok=True)
        pending = [
            (name, url) for name, url in MODEL_URLS.items()
            if not self._already_downloaded(home, name, url)
        ]

        for i, (name, url) in enumerate(pending, 1):
            label = name.replace("_", " ")
            self.status.emit(f"Downloading {label} ({i}/{len(pending)})…")
            try:
                self._download(requests, home, name, url)
            except Exception as exc:
                self.error.emit(f"Failed to download {name}: {exc}")
                return

        self.finished.emit()

    def _already_downloaded(self, home: Path, name: str, url: str) -> bool:
        saved_model = home / f"{name}_model" / "saved_model.pb"
        version_file = home / f"{name}_model" / ".model_url"
        if not saved_model.exists():
            return False
        if version_file.exists() and version_file.read_text().strip() != url:
            return False
        return True

    def _download(self, requests, home: Path, name: str, url: str) -> None:
        zip_path = home / f"_{name}.zip"
        resp = requests.get(url, stream=True, allow_redirects=True)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))

        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)

        self.status.emit(f"Extracting {name.replace('_', ' ')}…")
        self.progress.emit(0, 0)  # switch to indeterminate during extraction
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(str(home))
        zip_path.unlink(missing_ok=True)

        model_dir = home / f"{name}_model"
        model_dir.mkdir(exist_ok=True)
        (model_dir / ".model_url").write_text(url)
