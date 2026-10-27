"""Transcription des lignes MRZ en texte.

Le modèle de reconnaissance (CTC) fusionne les caractères identiques consécutifs quand ils
sont trop serrés, ce qui raccourcit les suites de `<`. Chaque ligne est donc étirée
horizontalement jusqu'à un pas fixe par caractère avant la reconnaissance (voir ADR 0003).
"""

from collections.abc import Sequence
from typing import Any, Protocol

import cv2
import numpy as np
from cv2.typing import MatLike

_TARGET_HEIGHT = 48
_GLYPH_HEIGHT_RATIO = 0.42  # hauteur de l'encre dans l'image envoyée au modèle
_PITCH_PER_HEIGHT = 1.05  # pas cible d'un caractère, rapporté à la hauteur de l'image
_MARGIN_RATIO = 0.4

_MRZ_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
# Signes que le modèle substitue parfois à `<` : guillemets simples et doubles, chevrons.
_LOOKALIKES = str.maketrans(
    {"\u00ab": "<<", "\u2039": "<", "\u3008": "<", "\u226a": "<<", "(": "<"}
)


class LineRecognizer(Protocol):
    def recognize(self, images: Sequence[MatLike]) -> list[str]: ...


class PaddleLineRecognizer:
    """PaddleOCR, reconnaissance seule : les lignes sont déjà localisées par `vision`."""

    MODEL_NAME = "en_PP-OCRv5_mobile_rec"

    def __init__(self, *, cpu_threads: int | None = None) -> None:
        self._model: Any = None
        self._options: dict[str, Any] = {} if cpu_threads is None else {"cpu_threads": cpu_threads}

    def _load(self) -> Any:
        if self._model is None:
            # Import tardif : dépendance lourde, installée avec l'extra `ocr`.
            from paddleocr import TextRecognition

            self._model = TextRecognition(model_name=self.MODEL_NAME, **self._options)
        return self._model

    def recognize(self, images: Sequence[MatLike]) -> list[str]:
        model = self._load()
        results = model.predict(input=list(images), batch_size=len(images))
        return [str(result["rec_text"]) for result in results]


def expected_length(line_count: int, line: MatLike) -> int:
    """30 pour 3 lignes ; pour 2 lignes, 36 (ancienne CNI) ou 44 (passeport) selon la forme."""
    if line_count == 3:
        return 30
    height, width = line.shape[:2]
    return 44 if width / height > 40 else 36


def prepare_line(line: MatLike, length: int) -> MatLike:
    """Ligne serrée sur l'encre → image au format attendu par le modèle, pas fixe."""
    glyph_height = line.shape[0]
    scale_y = _TARGET_HEIGHT * _GLYPH_HEIGHT_RATIO / glyph_height
    target_ink_width = length * _TARGET_HEIGHT * _PITCH_PER_HEIGHT
    resized = cv2.resize(
        line,
        (round(target_ink_width), max(1, round(glyph_height * scale_y))),
        interpolation=cv2.INTER_CUBIC,
    )
    pad_y = (_TARGET_HEIGHT - resized.shape[0]) // 2
    pad_x = round(_TARGET_HEIGHT * _MARGIN_RATIO)
    background = int(np.median(np.concatenate([line[0], line[-1]])))
    padded = cv2.copyMakeBorder(
        resized,
        pad_y,
        _TARGET_HEIGHT - resized.shape[0] - pad_y,
        pad_x,
        pad_x,
        cv2.BORDER_CONSTANT,
        value=(background, background, background),
    )
    return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)


def clean_text(text: str, length: int) -> str:
    """Majuscules, sans espaces ; suites de `<` finales ajustées à la longueur attendue."""
    cleaned = text.translate(_LOOKALIKES).upper().replace(" ", "")
    # Bord du document ou trait parasite lu en bout de ligne (`|`, `[`…).
    start, end = 0, len(cleaned)
    while start < end and cleaned[start] not in _MRZ_ALPHABET:
        start += 1
    while end > start and cleaned[end - 1] not in _MRZ_ALPHABET:
        end -= 1
    cleaned = cleaned[start:end]
    if len(cleaned) < length and cleaned.endswith("<"):
        return cleaned + "<" * (length - len(cleaned))
    if len(cleaned) > length and cleaned[length:].strip("<") == "":
        return cleaned[:length]
    return cleaned


def _length_from_texts(texts: Sequence[str]) -> int:
    """Pour 2 lignes : la plus longue transcription tranche entre 36 et 44 caractères."""
    return 44 if max(len(t.replace(" ", "")) for t in texts) >= 40 else 36


def read_lines(lines: Sequence[MatLike], recognizer: LineRecognizer) -> list[str]:
    length = expected_length(len(lines), lines[0])
    texts = recognizer.recognize([prepare_line(line, length) for line in lines])
    if len(lines) == 2 and (measured := _length_from_texts(texts)) != length:
        # Proportions trompeuses : on relit avec l'étirement adapté à la bonne longueur.
        length = measured
        texts = recognizer.recognize([prepare_line(line, length) for line in lines])
    return [clean_text(text, length) for text in texts]
