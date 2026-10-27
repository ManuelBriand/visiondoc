"""Détection du document et de la MRZ sur des photos synthétiques (sans modèle d'OCR)."""

import random

import cv2
import numpy as np
import pytest

from inference.synth.documents import (
    Capture,
    DocumentKind,
    Fonts,
    make_specimen,
    mrz_lines,
    photograph,
    random_identity,
    render_document,
)
from inference.vision.document import crop_document
from inference.vision.file_check import load_image
from inference.vision.mrz_locate import locate_mrz

KINDS: list[DocumentKind] = ["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"]
ASPECT = {
    "fr_id_card_2021": 1011 / 638,
    "fr_id_card_legacy": 1011 / 638,
    "fr_passport": 1476 / 1039,
}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("upside_down", [False, True])
def test_document_cropped_and_mrz_lines_found(
    kind: DocumentKind, upside_down: bool, fonts: Fonts
) -> None:
    for seed in range(3):
        specimen = make_specimen(kind, random.Random(seed), fonts, Capture(upside_down=upside_down))
        crop = crop_document(load_image(specimen.image))
        assert crop.found
        height, width = crop.image.shape[:2]
        assert width / height == pytest.approx(ASPECT[kind], rel=0.06)

        located = locate_mrz(crop.image)
        assert located is not None
        assert len(located.lines) == len(specimen.mrz)
        heights = [line.shape[0] for line in located.lines]
        assert max(heights) < 2 * min(heights)


def test_flat_scan_without_background_is_used_as_is(fonts: Fonts) -> None:
    rng = random.Random(4)
    lines = mrz_lines("fr_passport", random_identity(rng, "fr_passport"))
    document = render_document("fr_passport", lines, fonts, rng)
    ok, encoded = cv2.imencode(".png", document)
    assert ok
    crop = crop_document(load_image(encoded.tobytes()))
    located = locate_mrz(crop.image)
    assert located is not None
    assert len(located.lines) == 2


def test_document_without_mrz(fonts: Fonts) -> None:
    rng = random.Random(5)
    lines = mrz_lines("fr_id_card_2021", random_identity(rng, "fr_id_card_2021"))
    document = render_document("fr_id_card_2021", lines, fonts, rng)
    document[-230:] = np.median(document[-230:], axis=(0, 1)).astype(np.uint8)
    crop = crop_document(load_image(photograph(document, rng)))
    assert locate_mrz(crop.image) is None


@pytest.mark.parametrize("kind", KINDS)
def test_identity_generation_never_fails(kind: DocumentKind) -> None:
    for seed in range(2000):
        random_identity(random.Random(seed), kind)


@pytest.mark.parametrize("angle", [30.0, 45.0, 60.0, 90.0])
def test_document_rotated_by_large_angle_is_cropped_as_landscape(
    angle: float, fonts: Fonts
) -> None:
    specimen = make_specimen("fr_passport", random.Random(9), fonts, Capture(angle=angle))
    crop = crop_document(load_image(specimen.image))
    assert crop.found
    height, width = crop.image.shape[:2]
    assert width / height == pytest.approx(ASPECT["fr_passport"], rel=0.06)
    located = locate_mrz(crop.image)
    assert located is not None
    assert len(located.lines) == 2
