"""Extraction complète d'une pièce : une ou deux faces → réponse du contrat d'API (spec A3)."""

import time
from datetime import date

import cv2
from cv2.typing import MatLike

from inference.errors import ExtractionError
from inference.ocr.mrz_reader import LineRecognizer
from inference.ocr.text_engine import TextBox, TextEngine
from inference.pipeline.fusion import document_type, fuse
from inference.pipeline.models import Extraction, MrzSummary
from inference.pipeline.read_mrz import MrzRead, read_mrz
from inference.pipeline.visual_fields import VisualValue, count_labels, read_fields
from inference.timing import stage
from inference.vision.document import crop_document
from inference.vision.file_check import load_image
from inference.vision.quality import ensure_readable

_MIN_LABELS_FOR_ORIENTATION = 3


def _read_mrz_any_side(
    front: bytes, back: bytes | None, recognizer: LineRecognizer, today: date
) -> tuple[MrzRead, bytes | None]:
    """La MRZ est au verso de la nouvelle CNI : on essaie le recto, puis le verso."""
    try:
        return read_mrz(front, recognizer, today=today), back
    except ExtractionError as exc:
        if exc.code != "mrz_not_found" or back is None:
            raise
    return read_mrz(back, recognizer, today=today), front


def _read_other_side(data: bytes, engine: TextEngine) -> list[TextBox]:
    """Face sans MRZ : son orientation est celle où le plus de libellés sont reconnus."""
    with stage("file"):
        image = load_image(data)
    with stage("document"):
        crop = crop_document(image)
        ensure_readable(crop.image, crop.source_width)
    side: MatLike = crop.image
    if side.shape[0] > side.shape[1]:
        side = cv2.rotate(side, cv2.ROTATE_90_CLOCKWISE)
    with stage("visual_ocr"):
        boxes = engine.read(side)
    if count_labels(boxes) >= _MIN_LABELS_FOR_ORIENTATION:
        return boxes
    with stage("visual_ocr"):
        flipped = engine.read(cv2.rotate(side, cv2.ROTATE_180))
    return flipped if count_labels(flipped) > count_labels(boxes) else boxes


def extract(
    front: bytes,
    back: bytes | None,
    recognizer: LineRecognizer,
    engine: TextEngine,
    *,
    today: date | None = None,
) -> Extraction:
    started = time.perf_counter()
    reference = today or date.today()
    read, other = _read_mrz_any_side(front, back, recognizer, reference)
    kind = document_type(read.mrz)
    if kind is None:
        raise ExtractionError(
            "unsupported_document", "Seules la CNI et le passeport français sont acceptés."
        )

    # Les deux faces sont lues séparément : leurs coordonnées ne se mélangent pas.
    with stage("visual_ocr"):
        boxes = engine.read(read.document)
    visual: dict[str, VisualValue] = read_fields(boxes)
    if other is not None:
        for name, value in read_fields(_read_other_side(other, engine)).items():
            visual.setdefault(name, value)

    with stage("fusion"):
        fields, checks, warnings = fuse(read.mrz, visual, reference)
    return Extraction(
        document_type=kind,
        issuing_country=read.mrz.issuing_country,
        fields=fields,
        mrz=MrzSummary(
            raw=list(read.mrz.raw),
            format=read.mrz.format.value,
            checksums_valid=read.mrz.checksums_valid,
        ),
        checks=checks,
        warnings=warnings,
        processing_ms=round((time.perf_counter() - started) * 1000),
    )
