"""Lecture réelle avec PaddleOCR : lent (chargement du modèle), exécuté avec `pytest -m slow`."""

import random
from datetime import date

import pytest

from inference.errors import ExtractionError
from inference.ocr.mrz_reader import PaddleLineRecognizer
from inference.ocr.text_engine import PaddleTextEngine
from inference.pipeline.extract import extract
from inference.pipeline.read_mrz import read_mrz
from inference.synth.documents import Capture, DocumentKind, Fonts, make_specimen
from inference.text import fold, normalize_name

pytestmark = pytest.mark.slow

TODAY = date(2026, 10, 22)


@pytest.fixture(scope="module")
def recognizer() -> PaddleLineRecognizer:
    pytest.importorskip("paddleocr")
    return PaddleLineRecognizer()


@pytest.mark.parametrize("kind", ["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"])
def test_sharp_specimens_are_read(
    kind: DocumentKind, recognizer: PaddleLineRecognizer, fonts: Fonts
) -> None:
    rng = random.Random(2026)
    valid = 0
    for index in range(6):
        specimen = make_specimen(kind, rng, fonts, Capture(upside_down=index % 3 == 2))
        try:
            mrz = read_mrz(specimen.image, recognizer, today=TODAY).mrz
        except ExtractionError:
            continue
        if mrz.checksums_valid:
            valid += 1
            # Clés valides : la lecture doit être exacte (aucune erreur silencieuse).
            assert mrz.document_number == specimen.identity.document_number
            assert mrz.last_name == normalize_name(specimen.identity.last_name)
    assert valid >= 5


@pytest.fixture(scope="module")
def engine() -> PaddleTextEngine:
    pytest.importorskip("paddleocr")
    return PaddleTextEngine()


@pytest.mark.parametrize("kind", ["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"])
def test_full_extraction(
    kind: DocumentKind, recognizer: PaddleLineRecognizer, engine: PaddleTextEngine, fonts: Fonts
) -> None:
    rng = random.Random(7)
    exact = 0
    for _ in range(3):
        specimen = make_specimen(kind, rng, fonts)
        front, back = specimen.image, specimen.other_image
        if kind == "fr_id_card_2021":
            front, back = back or b"", front
        result = extract(front, back, recognizer, engine, today=TODAY)
        place = result.fields.get("birth_place")
        issue = result.fields.get("issue_date")
        if (
            place is not None
            and place.value == fold(specimen.birth_place)
            and issue is not None
            and issue.value == specimen.issue_date.isoformat()
            and result.fields["birth_date"].value == specimen.identity.birth_date.isoformat()
        ):
            exact += 1
    assert exact >= 2
