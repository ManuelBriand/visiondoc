"""Orchestration de l'extraction, avec un lecteur de MRZ et un moteur de texte factices."""

import random
from collections.abc import Sequence
from datetime import date

import pytest
from cv2.typing import MatLike

from inference.errors import ExtractionError
from inference.mrz.generator import MrzIdentity, build_td3
from inference.ocr.text_engine import TextBox
from inference.pipeline.extract import extract
from inference.synth.documents import Fonts, make_specimen, photograph, render_side

TODAY = date(2026, 10, 22)


class TruthRecognizer:
    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = list(lines)

    def recognize(self, images: Sequence[MatLike]) -> list[str]:
        return self.lines if len(images) == len(self.lines) else ["?"] * len(images)


class ScriptedEngine:
    """Renvoie, appel après appel, des lignes de texte fixées."""

    def __init__(self, *pages: list[TextBox]) -> None:
        self.pages = list(pages)
        self.calls = 0

    def read(self, image: MatLike) -> list[TextBox]:
        self.calls += 1
        return self.pages.pop(0) if self.pages else []


def _box(text: str, x: float, y: float) -> TextBox:
    return TextBox(text, 0.97, x, y, x + 300, y + 28)


def test_mrz_on_back_side_is_found_and_front_is_read(fonts: Fonts) -> None:
    specimen = make_specimen("fr_id_card_2021", random.Random(1), fonts)
    front = [
        _box("LIEU DE NAISSANCE / Place of birth", 700, 380),
        _box(specimen.birth_place, 700, 415),
        _box("NOM / Surname", 420, 120),
        _box(specimen.identity.last_name.upper(), 420, 155),
        _box("SEXE / Sex", 420, 300),
    ]
    back = [
        _box("DATE DE DÉLIVRANCE / Date of issue", 50, 150),
        _box(specimen.issue_date.strftime("%d %m %Y"), 50, 185),
    ]
    engine = ScriptedEngine(back, front)  # face MRZ lue d'abord, puis l'autre
    result = extract(
        specimen.other_image or b"",
        specimen.image,
        TruthRecognizer(specimen.mrz),
        engine,
        today=TODAY,
    )
    assert result.document_type == "fr_id_card_2021"
    assert result.issuing_country == "FRA"
    assert result.fields["birth_place"].source == "ocr"
    assert result.fields["issue_date"].value == specimen.issue_date.isoformat()
    assert result.fields["issue_date"].confidence == 0.9  # cohérente avec l'expiration
    assert result.mrz.format == "TD1"
    assert result.mrz.checksums_valid
    assert {c.code: c.status for c in result.checks}["mrz_matches_visual"] == "pass"
    assert result.processing_ms >= 0
    assert engine.calls == 2


def test_other_side_is_flipped_when_labels_are_missing(fonts: Fonts) -> None:
    specimen = make_specimen("fr_id_card_legacy", random.Random(2), fonts)
    upright = [
        _box(f"Carte valable jusqu'au : {specimen.printed_expiry:%d.%m.%Y}", 50, 200),
        _box(f"délivrée le : {specimen.issue_date:%d.%m.%Y}", 50, 260),
        _box("par : PRÉFECTURE", 50, 320),
    ]
    engine = ScriptedEngine([], [_box("ƎTꓘU⅁", 0, 0)], upright)
    result = extract(
        specimen.image,
        specimen.other_image,
        TruthRecognizer(specimen.mrz),
        engine,
        today=TODAY,
    )
    assert engine.calls == 3
    assert result.fields["issue_date"].value == specimen.issue_date.isoformat()
    assert "expiry_date" in result.fields


def test_passport_without_back(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(3), fonts)
    result = extract(
        specimen.image, None, TruthRecognizer(specimen.mrz), ScriptedEngine(), today=TODAY
    )
    assert result.document_type == "fr_passport"
    assert result.fields["document_number"].value == specimen.identity.document_number
    assert result.model_dump()["fields"]["birth_date"]["value"] == (
        specimen.identity.birth_date.isoformat()
    )


def test_foreign_passport_is_unsupported(fonts: Fonts) -> None:
    identity = MrzIdentity(
        last_name="Eriksson",
        first_names=("Anna",),
        document_number="L898902C3",
        birth_date=date(1974, 8, 12),
        sex="F",
        expiry_date=date(2030, 4, 15),
        issuing_country="UTO",
        nationality="UTO",
    )
    lines = build_td3(identity)
    rng = random.Random(4)
    image = photograph(render_side("fr_passport", [], fonts, rng, mrz=lines), rng)
    with pytest.raises(ExtractionError) as excinfo:
        extract(image, None, TruthRecognizer(lines), ScriptedEngine(), today=TODAY)
    assert excinfo.value.code == "unsupported_document"


def test_front_without_mrz_and_no_back_asks_for_back(fonts: Fonts) -> None:
    specimen = make_specimen("fr_id_card_2021", random.Random(5), fonts)
    with pytest.raises(ExtractionError) as excinfo:
        extract(
            specimen.other_image or b"",
            None,
            TruthRecognizer(specimen.mrz),
            ScriptedEngine(),
            today=TODAY,
        )
    assert excinfo.value.code == "mrz_not_found"
    assert "verso" in excinfo.value.message
