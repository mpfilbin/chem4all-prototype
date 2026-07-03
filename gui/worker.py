from __future__ import annotations
import logging
import os
from PyQt6.QtCore import QThread, pyqtSignal
from config import Config
from models.image_record import ImageRecord
from pipeline.recognizer import _run_decimer

log = logging.getLogger(__name__)


class RecognizerWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    record_ready = pyqtSignal(object)  # ImageRecord
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, records: list[ImageRecord], config: Config) -> None:
        super().__init__()
        self._records = records
        self._config = config

    def run(self) -> None:
        from pipeline.describer import describe_image
        from pipeline.namer import lookup_iupac, lookup_trivial_name
        api_key = os.environ.get("OPENROUTER_API_KEY") or self._config.openrouter_api_key
        total = len(self._records)
        for i, record in enumerate(self._records):

            if record.prediction_type == "description":
                self.status.emit(f"Describing {record.source_ref}  ({i + 1} of {total})…")
                try:
                    record.description = describe_image(record.recognition_bytes, api_key)
                except Exception as exc:
                    log.warning("Description failed for %s: %s", record.source_ref, exc)
                    self.error.emit(f"Could not describe {record.source_ref}: {exc}")
                finally:
                    record.recognition_bytes = b""
                self.progress.emit(i + 1, total)
                self.record_ready.emit(record)
                continue

            self.status.emit(f"Identifying {record.source_ref}  ({i + 1} of {total})…")
            try:
                smiles, confidence = _run_decimer(record.recognition_bytes)
                record.predicted_smiles = smiles
                record.confidence = confidence

                if record.prediction_type == "iupac" and smiles:
                    self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                    try:
                        record.iupac_name = lookup_iupac(smiles, api_key)
                    except Exception as exc:
                        log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                elif record.prediction_type == "trivial" and smiles:
                    self.status.emit(f"Looking up common name for {record.source_ref}…")
                    try:
                        record.trivial_name = lookup_trivial_name(smiles, api_key)
                    except Exception as exc:
                        log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

            except Exception as exc:
                log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                self.error.emit(f"Could not identify {record.source_ref}: {exc}")
                record.predicted_smiles = None
                record.confidence = None
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
