from __future__ import annotations
import logging
import os
import time
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
            types = set(record.prediction_types)
            try:
                if types & {"smiles", "iupac", "trivial"}:
                    self.status.emit(f"Identifying {record.source_ref}  ({i + 1} of {total})…")
                    smiles = None
                    try:
                        log.debug("Recognizing %s...", record.source_ref)
                        t0 = time.perf_counter()
                        smiles, confidence = _run_decimer(record.recognition_bytes)
                        log.debug("%s -> SMILES '%s' (%.2fs)", record.source_ref, smiles, time.perf_counter() - t0)
                        record.predicted_smiles = smiles
                        record.confidence = confidence
                    except Exception as exc:
                        log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Could not identify {record.source_ref}: {exc}")
                        record.predicted_smiles = None
                        record.confidence = None

                    if "iupac" in types and smiles:
                        self.status.emit(f"Looking up IUPAC name for {record.source_ref}…")
                        try:
                            log.debug("Looking up IUPAC name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.iupac_name = lookup_iupac(smiles, api_key)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.iupac_name, time.perf_counter() - t0)
                        except Exception as exc:
                            log.warning("IUPAC lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"IUPAC lookup failed for {record.source_ref}: {exc}")

                    if "trivial" in types and smiles:
                        self.status.emit(f"Looking up common name for {record.source_ref}…")
                        try:
                            log.debug("Looking up common name for %s...", record.source_ref)
                            t0 = time.perf_counter()
                            record.trivial_name = lookup_trivial_name(smiles, api_key)
                            log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.trivial_name, time.perf_counter() - t0)
                        except Exception as exc:
                            log.warning("Common name lookup failed for %s: %s", record.source_ref, exc)
                            self.error.emit(f"Common name lookup failed for {record.source_ref}: {exc}")

                if "description" in types:
                    self.status.emit(f"Describing {record.source_ref}  ({i + 1} of {total})…")
                    try:
                        log.debug("Describing %s...", record.source_ref)
                        t0 = time.perf_counter()
                        record.description = describe_image(record.recognition_bytes, api_key)
                        log.debug("%s -> '%s' (%.2fs)", record.source_ref, record.description, time.perf_counter() - t0)
                    except Exception as exc:
                        log.warning("Description failed for %s: %s", record.source_ref, exc)
                        self.error.emit(f"Could not describe {record.source_ref}: {exc}")

                if "decorative" in types:
                    self.status.emit(f"Skipping decorative image {record.source_ref}  ({i + 1} of {total})…")
            finally:
                record.recognition_bytes = b""

            self.progress.emit(i + 1, total)
            self.record_ready.emit(record)

        self.finished.emit()
