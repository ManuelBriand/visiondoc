"""Localisation de la bande MRZ et découpage en lignes.

La MRZ est un bloc de 2 ou 3 lignes très larges en bas du document. Le filtre « blackhat »
fait ressortir le texte sombre sur fond clair ; une fermeture horizontale soude les
caractères en bandes. La bande retenue est la plus basse parmi les bandes assez larges.
Trouvée en haut, elle indique un document à l'envers : on le retourne.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

_MIN_BAND_WIDTH_RATIO = 0.55
_MIN_LINE_HEIGHT_RATIO = 0.5


@dataclass(frozen=True)
class MrzLines:
    lines: tuple[MatLike, ...]  # une image en niveaux de gris par ligne, serrée sur l'encre
    document: MatLike  # document dans le bon sens


def _bands(gray: MatLike) -> list[tuple[int, int, int, int]]:
    width = gray.shape[1]
    rect = cv2.getStructuringElement(cv2.MORPH_RECT, (round(width * 0.022), round(width * 0.008)))
    wide = cv2.getStructuringElement(cv2.MORPH_RECT, (round(width * 0.05), round(width * 0.02)))
    blackhat = cv2.morphologyEx(cv2.GaussianBlur(gray, (3, 3), 0), cv2.MORPH_BLACKHAT, rect)
    grad = np.absolute(cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=-1))
    grad = cv2.normalize(grad, np.empty_like(grad), 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    closed = cv2.morphologyEx(grad, cv2.MORPH_CLOSE, rect)
    _, mask = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, wide)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=2)
    # Le liseré de fond laissé par le recadrage se souderait à la MRZ : on vide les bords.
    border = round(width * 0.015)
    mask[:border, :] = mask[-border:, :] = 0
    mask[:, :border] = mask[:, -border:] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= _MIN_BAND_WIDTH_RATIO * width and w > 4 * h:
            boxes.append((x, y, w, h))
    return boxes


def _lowest_band(gray: MatLike) -> tuple[int, int, int, int] | None:
    """Bande la plus basse, fusionnée avec les bandes juste au-dessus (lignes non soudées)."""
    bands = sorted(_bands(gray), key=lambda b: b[1] + b[3], reverse=True)
    if not bands:
        return None
    x, y, w, h = bands[0]
    line_height = h
    for bx, by, bw, bh in bands[1:]:
        if y - (by + bh) > line_height:
            break
        x, w = min(x, bx), max(x + w, bx + bw) - min(x, bx)
        h, y = y + h - by, by
    return x, y, w, h


def _split_lines(band: MatLike) -> tuple[MatLike, ...]:
    _, ink = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    profile = ink.sum(axis=1) / 255
    active = profile > 0.08 * profile.max()
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, on in enumerate([*active.tolist(), False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            runs.append((start, y))
            start = None
    if not runs:
        return ()
    tallest = max(end - begin for begin, end in runs)
    runs = [r for r in runs if r[1] - r[0] >= _MIN_LINE_HEIGHT_RATIO * tallest]
    lines: list[MatLike] = []
    for begin, end in runs:
        columns = np.flatnonzero(ink[begin:end].sum(axis=0) > 0)
        lines.append(band[begin:end, columns[0] : columns[-1] + 1])
    return tuple(lines)


def _extract(gray: MatLike, box: tuple[int, int, int, int]) -> tuple[MatLike, ...]:
    x, y, w, h = box
    # Marge horizontale réduite : au-delà, on risque d'inclure le bord sombre du document.
    pad_y, pad_x = round(h * 0.15), round(w * 0.005)
    y0, y1 = max(0, y - pad_y), min(gray.shape[0], y + h + pad_y)
    x0, x1 = max(0, x - pad_x), min(gray.shape[1], x + w + pad_x)
    return _split_lines(gray[y0:y1, x0:x1])


def locate_mrz(document: MatLike) -> MrzLines | None:
    """Renvoie les lignes de la MRZ, document remis à l'endroit, ou `None`."""
    oriented = document
    if document.shape[0] > document.shape[1]:
        oriented = cv2.rotate(document, cv2.ROTATE_90_CLOCKWISE)
    for candidate in (oriented, cv2.rotate(oriented, cv2.ROTATE_180)):
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        box = _lowest_band(gray)
        if box is None or box[1] + box[3] / 2 < gray.shape[0] / 2:
            continue
        lines = _extract(gray, box)
        if len(lines) in (2, 3):
            return MrzLines(lines=lines, document=candidate)
    return None
