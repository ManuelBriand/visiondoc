"""Détection des bords du document et redressement de la perspective."""

from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

# Largeur du document redressé ; la hauteur suit les proportions mesurées.
NORMALIZED_WIDTH = 1200
_DETECTION_WIDTH = 800
_MIN_AREA_RATIO = 0.15


@dataclass(frozen=True)
class DocumentCrop:
    image: MatLike
    found: bool  # faux : aucun contour net, l'image entière est utilisée (scan déjà recadré)
    cut: bool  # le document principal sort du cadre par un à trois côtés
    source_width: float  # largeur du document dans l'image d'origine, en pixels


def _order_corners(points: MatLike) -> MatLike:
    """Coins dans le sens horaire, en commençant par un grand côté : le document redressé est
    toujours en paysage. Le tri par angle autour du centre reste juste à 45°, là où un tri
    par somme des coordonnées hésite entre deux coins. L'éventuel retournement de 180° est
    corrigé ensuite (MRZ en bas, ou libellés lisibles)."""
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = pts.mean(axis=0)
    pts = pts[np.argsort(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))]
    lengths = [float(np.linalg.norm(pts[(i + 1) % 4] - pts[i])) for i in range(4)]
    starts = [i for i in range(4) if lengths[i] >= lengths[(i + 1) % 4]]
    start = min(starts, key=lambda i: float(pts[i].sum()))
    return np.roll(pts, -start, axis=0)


def _touched_borders(contour: MatLike, width: int, height: int) -> int:
    x, y, w, h = cv2.boundingRect(contour)
    margin = 3
    return sum((x <= margin, y <= margin, x + w >= width - margin, y + h >= height - margin))


def _is_cut(gray: MatLike) -> bool:
    """La plus grande région claire (le document, sur un fond plus sombre) sort-elle du cadre ?

    Un contour ouvert par le bord de l'image n'a pas de surface : on segmente donc par
    luminosité. Un document sur fond clair n'est pas détecté ; il finit en `mrz_not_found`.
    """
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest = max(contours, key=cv2.contourArea, default=None)
    if largest is None or cv2.contourArea(largest) < _MIN_AREA_RATIO * gray.size:
        return False
    return 0 < _touched_borders(largest, gray.shape[1], gray.shape[0]) < 4


def _find_quad(image: MatLike) -> tuple[MatLike | None, bool]:
    """Coins du document, et vrai si le document sort du cadre (photo coupée)."""
    height, width = image.shape[:2]
    ratio = width / _DETECTION_WIDTH
    small = cv2.resize(image, (_DETECTION_WIDTH, round(height / ratio)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 30, 120), np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = _MIN_AREA_RATIO * small.shape[0] * small.shape[1]
    largest = max(contours, key=cv2.contourArea, default=None)
    if (
        largest is None
        or cv2.contourArea(largest) < min_area
        or _touched_borders(largest, small.shape[1], small.shape[0]) > 0
    ):
        return None, _is_cut(gray)
    hull = cv2.convexHull(largest)
    approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
    points = approx if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(hull))
    return np.asarray(_order_corners(points) * ratio, dtype=np.float32), False


def crop_document(image: MatLike) -> DocumentCrop:
    corners, cut = _find_quad(image)
    if corners is None:
        height, width = image.shape[:2]
        scale = NORMALIZED_WIDTH / width
        resized = cv2.resize(image, (NORMALIZED_WIDTH, round(height * scale)))
        return DocumentCrop(image=resized, found=False, cut=cut, source_width=float(width))
    tl, tr, br, bl = corners
    doc_width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    doc_height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    out_width = NORMALIZED_WIDTH
    out_height = round(NORMALIZED_WIDTH * doc_height / doc_width)
    target = np.array(
        [[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners, target)
    warped = cv2.warpPerspective(image, matrix, (out_width, out_height), flags=cv2.INTER_CUBIC)
    return DocumentCrop(image=warped, found=True, cut=False, source_width=float(doc_width))
