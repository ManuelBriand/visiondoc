"""Chaîne complète de l'étape 2, avec un lecteur factice qui renvoie la vérité terrain.

Le vrai modèle est couvert par `test_paddle_integration.py` (marqueur `slow`).
"""

import random
from collections.abc import Sequence
from datetime import date

import pytest
from cv2.typing import MatLike

from inference.errors import ExtractionError, ImageUnreadableError
from inference.pipeline.read_mrz import read_mrz
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

TODAY = date(2026, 10, 22)


class TruthRecognizer:
    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = list(lines)

    def recognize(self, images: Sequence[MatLike]) -> list[str]:
        assert len(images) == len(self.lines)
        return self.lines


@pytest.mark.parametrize("kind", ["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"])
def test_reads_mrz_from_photo(kind: DocumentKind, fonts: Fonts) -> None:
    specimen = make_specimen(kind, random.Random(1), fonts, Capture(upside_down=True))
    read = read_mrz(specimen.image, TruthRecognizer(specimen.mrz), today=TODAY)
    assert read.mrz.checksums_valid
    assert read.mrz.document_number == specimen.identity.document_number
    assert read.mrz.birth_date == specimen.identity.birth_date


def test_blurry_photo_is_refused(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(2), fonts, Capture(blur_sigma=3.5))
    with pytest.raises(ExtractionError) as excinfo:
        read_mrz(specimen.image, TruthRecognizer(specimen.mrz), today=TODAY)
    assert excinfo.value.code == "image_unreadable"
    assert "floue" in excinfo.value.message


def test_unreadable_text_gives_mrz_not_found(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(3), fonts)
    with pytest.raises(ExtractionError) as excinfo:
        read_mrz(specimen.image, TruthRecognizer(["N0T A MRZ", "AT ALL"]), today=TODAY)
    assert excinfo.value.code == "mrz_not_found"
    assert "verso" in excinfo.value.message


def test_cut_document_without_mrz_is_reported_as_cropped(fonts: Fonts) -> None:
    rng = random.Random(4)
    lines = mrz_lines("fr_id_card_2021", random_identity(rng, "fr_id_card_2021"))
    document = render_document("fr_id_card_2021", lines, fonts, rng)
    # Document décalé vers le bas : la MRZ sort du cadre.
    image = photograph(document, rng, Capture(shift=(0.0, 0.42)))
    with pytest.raises(ImageUnreadableError) as excinfo:
        read_mrz(image, TruthRecognizer(lines), today=TODAY)
    assert excinfo.value.cause == "cropped"


def test_failed_read_on_dim_photo_is_explained_as_too_dark(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(6), fonts, Capture(brightness=0.22))
    with pytest.raises(ImageUnreadableError) as excinfo:
        read_mrz(specimen.image, TruthRecognizer(["ILLISIBLE", "ILLISIBLE"]), today=TODAY)
    assert excinfo.value.cause == "too_dark"


def test_overexposed_but_readable_photo_is_accepted(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(7), fonts, Capture(brightness=1.6))
    read = read_mrz(specimen.image, TruthRecognizer(specimen.mrz), today=TODAY)
    assert read.mrz.checksums_valid
    assert read.quality.saturated_ratio > 0.5
