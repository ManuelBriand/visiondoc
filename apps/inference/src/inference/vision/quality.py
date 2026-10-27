"""Mesures de qualité sur le document redressé.

Deux niveaux (ADR 0006) :
- refus immédiat de ce qui est certainement illisible (trop petit, flou, très sombre) ;
- au-delà, on tente la lecture ; si elle échoue, `likely_cause` explique l'échec au
  demandeur par la cause la plus probable (pénombre, surexposition, léger flou).
Refuser d'emblée une photo lisible coûte un dossier : une surexposition uniforme, par
exemple, sature le fond de la carte mais laisse le texte parfaitement lisible.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

from inference.errors import ImageUnreadableError, UnreadableCause

# Seuils calibrés sur les spécimens synthétiques (ADR 0006), à revoir sur de vraies photos.
MIN_SOURCE_WIDTH = 500.0
MIN_SHARPNESS = 20.0
MIN_BRIGHTNESS = 25.0
# Seuils d'explication d'un échec de lecture (aucun refus par eux-mêmes).
DOUBTFUL_SHARPNESS = 60.0
DOUBTFUL_BRIGHTNESS = 60.0
DOUBTFUL_SATURATED_RATIO = 0.5


@dataclass(frozen=True)
class QualityReport:
    sharpness: float  # variance du laplacien, document ramené à 1 200 px de large
    brightness: float  # niveau de gris moyen
    saturated_ratio: float  # part des pixels blancs saturés

    def cause(self, source_width: float) -> UnreadableCause | None:
        """Cause d'un refus immédiat : la photo est certainement illisible."""
        if source_width < MIN_SOURCE_WIDTH:
            return "too_small"
        if self.brightness < MIN_BRIGHTNESS:
            return "too_dark"
        if self.sharpness < MIN_SHARPNESS:
            return "blurry"
        return None

    def likely_cause(self) -> UnreadableCause | None:
        """Explication la plus probable d'une lecture qui a échoué."""
        if self.brightness < DOUBTFUL_BRIGHTNESS:
            return "too_dark"
        if self.saturated_ratio > DOUBTFUL_SATURATED_RATIO:
            return "overexposed"
        if self.sharpness < DOUBTFUL_SHARPNESS:
            return "blurry"
        return None


def measure(document: MatLike) -> QualityReport:
    gray = cv2.cvtColor(document, cv2.COLOR_BGR2GRAY)
    return QualityReport(
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        brightness=float(gray.mean()),
        saturated_ratio=float(np.count_nonzero(gray >= 250) / gray.size),
    )


def ensure_readable(document: MatLike, source_width: float) -> QualityReport:
    report = measure(document)
    cause = report.cause(source_width)
    if cause is not None:
        raise ImageUnreadableError(cause)
    return report
