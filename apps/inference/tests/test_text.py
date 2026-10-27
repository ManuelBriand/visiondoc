import pytest

from inference.text import compact, fold, normalize_label, normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Élodie", "ELODIE"), ("Gaëlle", "GAELLE"), ("NÎMES", "NIMES"), ("ça", "CA")],
)
def test_fold(raw: str, expected: str) -> None:
    assert fold(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("N° DU DOCUMENT / Document No", "N DU DOCUMENT DOCUMENT NO"),
        ("DATE D'EXPIR. / Expiry date", "DATE D EXPIR EXPIRY DATE"),
        ("Né(e) le :", "NE E LE"),
        ("Prénom(s)", "PRENOM S"),
    ],
)
def test_normalize_label(raw: str, expected: str) -> None:
    assert normalize_label(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Jean-Pierre", "JEAN PIERRE"),
        ("N'Diaye", "N DIAYE"),
        ("  de la   Fontaine ", "DE LA FONTAINE"),
        ("Lefèvre", "LEFEVRE"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_compact() -> None:
    assert compact("De La Fontaine") == compact("DELAFONTAINE")
