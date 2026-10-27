from datetime import date

import pytest

from inference.ocr.text_engine import TextBox
from inference.pipeline.visual_fields import count_labels, parse_date, read_fields


def box(text: str, x: float, y: float, width: float = 200, height: float = 28) -> TextBox:
    return TextBox(text, 0.98, x, y, x + width, y + height)


def values(boxes: list[TextBox]) -> dict[str, object]:
    return {name: field.value for name, field in read_fields(boxes).items()}


def test_labels_above_values_new_id_card() -> None:
    boxes = [
        box("RÉPUBLIQUE FRANÇAISE", 400, 30, 300),
        box("NOM / Surname", 420, 120),
        box("MARTIN", 420, 155),
        box("Prénoms / Given names", 420, 210),
        box("Camille, Marie", 420, 245),
        box("SEXE / Sex", 420, 300),
        box("F", 420, 335, 20),
        box("NATIONALITÉ / Nationality", 790, 300),
        box("FRA", 790, 335, 60),
        box("DATE DE NAISS. / Date of birth", 420, 390),
        box("12 04 1990", 420, 425),
        box("LIEU DE NAISSANCE / Place of birth", 790, 390),
        box("SAINT-ÉTIENNE", 790, 425),
        box("N° DU DOCUMENT / Document No", 60, 480),
        box("X4RTBPFW4", 60, 515),
        box("DATE D'EXPIR. / Expiry date", 790, 480),
        box("30 06 2031", 790, 515),
    ]
    assert values(boxes) == {
        "last_name": "MARTIN",
        "first_names": ("CAMILLE", "MARIE"),
        "sex": "F",
        "birth_date": date(1990, 4, 12),
        "birth_place": "SAINT-ETIENNE",
        "document_number": "X4RTBPFW4",
        "expiry_date": date(2031, 6, 30),
    }


def test_inline_labels_legacy_id_card() -> None:
    boxes = [
        box("CARTE NATIONALE D'IDENTITÉ N° : 880692310285", 330, 70, 600),
        box("Nom : N'DIAYE", 330, 150, 300),
        box("Prénom(s) : Maëlle, Odile", 330, 210, 400),
        box("Sexe : F", 330, 270),
        box("Taille : 1,72 m", 660, 270),
        box("Né(e) le : 20.12.1963", 330, 330, 300),
        box("à : NÎMES (30)", 330, 390),
        box("Carte valable jusqu'au : 24.07.2022", 50, 450, 500),
        box("délivrée le : 24.07.2012", 50, 510, 400),
        box("par : PRÉFECTURE DU FINISTÈRE", 50, 570, 500),
    ]
    assert values(boxes) == {
        "document_number": "880692310285",
        "last_name": "N DIAYE",
        "first_names": ("MAELLE", "ODILE"),
        "sex": "F",
        "birth_date": date(1963, 12, 20),
        "birth_place": "NIMES",
        "expiry_date": date(2022, 7, 24),
        "issue_date": date(2012, 7, 24),
    }


def test_merged_labels_are_split() -> None:
    # Deux libellés voisins fusionnés par l'OCR en une seule ligne.
    boxes = [
        box("Date de délivrance / Date of issue Date d'expiration / Date of expiry", 597, 586, 592),
        box("30 09 2013", 597, 628, 150),
        box("30 09 2023", 895, 628, 150),
        box("Code du pays / Country code Passeport n° / Passport No.", 598, 107, 501),
        box("FRA", 593, 145, 64),
        box("21UN23199", 859, 148, 160),
    ]
    assert values(boxes) == {
        "issue_date": date(2013, 9, 30),
        "expiry_date": date(2023, 9, 30),
        "document_number": "21UN23199",
    }


def test_mrz_lines_and_unknown_labels_are_ignored() -> None:
    boxes = [
        box("ADRESSE / Address", 50, 40),
        box("12 RUE DES LILAS 69003 LYON", 50, 75, 400),
        box("P<FRAMARTIN<<CAMILLE<<<<<<<<<<<<<<", 50, 600, 1000),
    ]
    assert values(boxes) == {}


def test_value_on_the_right_of_its_label() -> None:
    boxes = [box("Nom / Surname", 50, 100, 150), box("MARTIN", 230, 101, 120)]
    assert values(boxes) == {"last_name": "MARTIN"}


def test_label_without_value() -> None:
    assert values([box("NOM / Surname", 50, 100)]) == {}


def test_value_too_far_below_is_not_taken() -> None:
    assert values([box("NOM / Surname", 50, 100), box("MARTIN", 50, 400)]) == {}


def test_misread_long_label_still_matches() -> None:
    boxes = [box("LIEU DE NAlSSANCE / Place of birth", 50, 100), box("LYON", 50, 135)]
    assert values(boxes) == {"birth_place": "LYON"}


def test_short_labels_require_exact_match() -> None:
    # « NON » n'est pas « NOM » : les libellés courts ne tolèrent aucune erreur.
    assert values([box("NON", 50, 100), box("MARTIN", 50, 135)]) == {}


def test_value_that_begins_like_a_label_is_a_value() -> None:
    boxes = [box("LIEU DE NAISSANCE / Place of birth", 50, 100), box("PARIS", 50, 135)]
    assert values(boxes) == {"birth_place": "PARIS"}


def test_count_labels() -> None:
    assert count_labels([box("NOM / Surname", 0, 0), box("MARTIN", 0, 40)]) == 1
    assert count_labels([box("ƎMANᴚUS / MON", 0, 0)]) == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12 04 1990", date(1990, 4, 12)),
        ("12.04.1990", date(1990, 4, 12)),
        ("12/04/1990", date(1990, 4, 12)),
        ("I2 O4 199O", date(1990, 4, 12)),  # confusions de l'OCR
        ("12 AVR 1990", date(1990, 4, 12)),
        ("12 AVR. 1990", date(1990, 4, 12)),
        ("1 févr 2001", date(2001, 2, 1)),
        ("31 02 1990", None),
        ("12 04 1790", None),
        ("pas une date", None),
    ],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected
