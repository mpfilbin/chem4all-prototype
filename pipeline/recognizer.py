from __future__ import annotations
import logging
from config import Config
from models.image_record import ImageRecord

log = logging.getLogger(__name__)


def _run_decimer(img_bytes: bytes) -> tuple[str | None, float | None]:
    from DECIMER import predict_SMILES  # deferred import; heavy model load
    import io
    import numpy as np
    from PIL import Image
    img_array = np.array(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
    smiles = predict_SMILES(img_array)
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
