from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from config import Config
from models.image_record import ImageRecord


class ExtractorWorker(QThread):
    finished = pyqtSignal(list)      # list[ImageRecord]
    progress = pyqtSignal(int, int)  # extracted, total
    error = pyqtSignal(str)

    def __init__(self, file_path: Path, config: Config) -> None:
        super().__init__()
        self._file_path = file_path
        self._config = config

    def run(self) -> None:
        try:
            from pipeline.extractor import extract
            records = extract(self._file_path, self._config, on_progress=self.progress.emit)
            self.finished.emit(records)
        except Exception as exc:
            self.error.emit(str(exc))
