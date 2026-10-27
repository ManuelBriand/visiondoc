"""OCR de la zone visuelle : détection et reconnaissance des lignes de texte."""

from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np
from cv2.typing import MatLike


@dataclass(frozen=True)
class TextBox:
    text: str
    score: float  # confiance du modèle de reconnaissance
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


_BATCH_SIZE = 8


class TextEngine(Protocol):
    def read(self, image: MatLike) -> list[TextBox]: ...


def crop_quad(image: MatLike, quad: MatLike) -> MatLike:
    """Ligne de texte redressée à partir de ses 4 coins (haut-gauche en premier)."""
    pts = np.asarray(quad, dtype=np.float32).reshape(4, 2)
    width = round(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[3] - pts[2])))
    height = round(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
    width, height = max(width, 1), max(height, 1)
    target = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(pts, target)
    line = cv2.warpPerspective(image, matrix, (width, height), flags=cv2.INTER_CUBIC)
    if height / width >= 1.5:  # texte vertical
        line = cv2.rotate(line, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return line


class PaddleTextEngine:
    """PaddleOCR : détection mobile, puis reconnaissance latine (accents français).

    Les deux modèles sont chargés séparément : sous Linux x86, PaddlePaddle 3.3 lève
    `NotImplementedError` sur le modèle de détection avec oneDNN, alors que la
    reconnaissance fonctionne avec et y gagne un facteur 5. oneDNN est donc désactivé pour
    la détection seule (ADR 0006).
    """

    DETECTION_MODEL = "PP-OCRv5_mobile_det"
    RECOGNITION_MODEL = "latin_PP-OCRv5_mobile_rec"

    def __init__(self, *, det_max_side: int | None = None, cpu_threads: int | None = None) -> None:
        """`det_max_side` : plus grand côté de l'image donnée à la détection (par défaut,
        la pleine résolution) ; `cpu_threads` : threads de calcul (10 par défaut)."""
        self._models: tuple[Any, Any] | None = None
        self._common: dict[str, Any] = {} if cpu_threads is None else {"cpu_threads": cpu_threads}
        self._detection: dict[str, Any] = {}
        if det_max_side is not None:
            self._detection = {"limit_type": "max", "limit_side_len": det_max_side}

    def _load(self) -> tuple[Any, Any]:
        if self._models is None:
            # Import tardif : dépendance lourde, installée avec l'extra `ocr`.
            from paddleocr import TextDetection, TextRecognition

            detector = TextDetection(
                model_name=self.DETECTION_MODEL,
                enable_mkldnn=False,
                **self._detection,
                **self._common,
            )
            recognizer = TextRecognition(model_name=self.RECOGNITION_MODEL, **self._common)
            self._models = (detector, recognizer)
        return self._models

    def read(self, image: MatLike) -> list[TextBox]:
        detector, recognizer = self._load()
        quads = list(detector.predict(image)[0]["dt_polys"])
        if not quads:
            return []
        lines = [crop_quad(image, quad) for quad in quads]
        # Lignes groupées par proportions : dans un lot, chaque ligne est complétée à la
        # largeur de la plus longue ; mêler courtes et longues dégrade lecture et vitesse.
        order = sorted(range(len(lines)), key=lambda i: lines[i].shape[1] / lines[i].shape[0])
        ranked = recognizer.predict(input=[lines[i] for i in order], batch_size=_BATCH_SIZE)
        results: list[Any] = [None] * len(lines)
        for position, result in zip(order, ranked, strict=True):
            results[position] = result
        boxes = []
        for quad, result in zip(quads, results, strict=True):
            pts = np.asarray(quad, dtype=np.float32).reshape(4, 2)
            boxes.append(
                TextBox(
                    str(result["rec_text"]),
                    float(result["rec_score"]),
                    float(pts[:, 0].min()),
                    float(pts[:, 1].min()),
                    float(pts[:, 0].max()),
                    float(pts[:, 1].max()),
                )
            )
        return sorted(boxes, key=lambda box: (round(box.y0 / 10), box.x0))
