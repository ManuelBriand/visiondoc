"""Étape 2 : d'un fichier reçu à une MRZ lue et validée."""

from dataclasses import dataclass
from datetime import date

from cv2.typing import MatLike

from inference.errors import ExtractionError, ImageUnreadableError
from inference.mrz import MrzError, MrzResult
from inference.mrz.repair import parse_mrz_tolerant
from inference.ocr.mrz_reader import LineRecognizer, read_lines
from inference.timing import stage
from inference.vision.document import crop_document
from inference.vision.file_check import load_image
from inference.vision.mrz_locate import locate_mrz
from inference.vision.quality import QualityReport, ensure_readable

_MRZ_NOT_FOUND = "MRZ absente ou illisible. Pour une CNI au nouveau format, envoyez aussi le verso."


@dataclass(frozen=True)
class MrzRead:
    mrz: MrzResult
    document: MatLike  # document redressé, dans le bon sens (pour l'OCR de la zone visuelle)
    quality: QualityReport


def _unreadable(cut: bool, quality: QualityReport) -> ExtractionError:
    """MRZ illisible : la cause la plus probable, sinon l'absence de MRZ."""
    if cut:
        return ImageUnreadableError("cropped")
    cause = quality.likely_cause()
    if cause is not None:
        return ImageUnreadableError(cause)
    return ExtractionError("mrz_not_found", _MRZ_NOT_FOUND)


def read_mrz(data: bytes, recognizer: LineRecognizer, *, today: date | None = None) -> MrzRead:
    with stage("file"):
        image = load_image(data)
    with stage("document"):
        crop = crop_document(image)
        quality = ensure_readable(crop.image, crop.source_width)
    with stage("mrz_locate"):
        located = locate_mrz(crop.image)
    if located is None:
        raise _unreadable(crop.cut, quality)
    with stage("mrz_ocr"):
        texts = read_lines(located.lines, recognizer)
    try:
        with stage("mrz_parse"):
            mrz = parse_mrz_tolerant(texts, today=today)
    except MrzError as exc:
        raise _unreadable(crop.cut, quality) from exc
    return MrzRead(mrz=mrz, document=located.document, quality=quality)
