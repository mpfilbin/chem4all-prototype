from __future__ import annotations
import logging
import time
from config import Config
from models.image_record import ImageRecord

log = logging.getLogger(__name__)

_decimer_loaded = False


def mark_decimer_loaded() -> None:
    global _decimer_loaded
    _decimer_loaded = True


def _run_decimer(img_bytes: bytes) -> tuple[str | None, float | None]:
    global _decimer_loaded
    import io
    import numpy as np
    from PIL import Image
    img_array = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))

    first_load = not _decimer_loaded
    if first_load:
        log.debug("Loading DECIMER model...")
        t0 = time.perf_counter()

    try:
        from DECIMER import predict_SMILES  # deferred import; heavy model load
        smiles = predict_SMILES(img_array)
    except Exception as exc:
        if first_load:
            log.warning("DECIMER model failed to load: %s", exc)
        raise

    if first_load:
        log.debug("DECIMER model loaded in %.2fs", time.perf_counter() - t0)
        _decimer_loaded = True

    # DECIMER does not expose a confidence score in the public API;
    # return 1.0 as a sentinel so auto-filter threshold comparisons still work.
    return (smiles if smiles else None, 1.0 if smiles else 0.0)


def recognize(records: list[ImageRecord], config: Config) -> list[ImageRecord]:
    for record in records:
        try:
            smiles, confidence = _run_decimer(record.recognition_bytes)
            record.predicted_smiles = smiles
            record.confidence = confidence
        except Exception as exc:
            log.warning("DECIMER failed for %s: %s", record.source_ref, exc)
            record.predicted_smiles = None
            record.confidence = None
        finally:
            record.recognition_bytes = b""
    return records
