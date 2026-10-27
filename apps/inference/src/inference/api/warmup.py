"""Chargement des modèles par une inférence à vide.

À la construction de l'image (`python -m inference.api.warmup`), il télécharge les modèles :
le conteneur démarre ensuite sans réseau. Au démarrage du serveur, il les charge en mémoire :
la première requête n'est pas pénalisée.
"""

import numpy as np

from inference.ocr.mrz_reader import LineRecognizer, PaddleLineRecognizer
from inference.ocr.text_engine import PaddleTextEngine, TextEngine


def warm(recognizer: LineRecognizer, engine: TextEngine) -> None:
    blank = np.full((64, 320, 3), 255, dtype=np.uint8)
    recognizer.recognize([blank])
    engine.read(blank)


if __name__ == "__main__":
    warm(PaddleLineRecognizer(), PaddleTextEngine())
    print("Modèles prêts.")
