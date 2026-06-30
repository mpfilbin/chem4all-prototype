from __future__ import annotations
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from config import Config
from models.image_record import ImageRecord
from pipeline.recognizer import _run_decimer

log = logging.getLogger(__name__)


class RecognizerWorker(QThread):
    progress = pyqtSignal(int, int)
    record_ready = pyqtSignal(object)  # ImageRecord
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, records: list[ImageRecord], config: Config) -> None:
        super().__init__()
        self._records = records
        self._config = config

    def run(self) -> None:
        total = len(self._records)
        for i, record in enumerate(self._records):
            try:
                smiles, confidence = _run_decimer(record.recognition_bytes)
                record.predicted_smiles = smiles
                record.confidence = confidence
                if self._config.auto_filter and confidence is not None and confidence < self._config.confidence_threshold:
                    record.is_chemical = False
            except Exception as exc:
                log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                record.predicted_smiles = None
                record.confidence = None
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
