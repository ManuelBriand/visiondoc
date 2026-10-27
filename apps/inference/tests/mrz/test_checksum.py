import pytest

from inference.mrz.checksum import char_value, check_digit, verify


@pytest.mark.parametrize(("char", "expected"), [("0", 0), ("9", 9), ("A", 10), ("Z", 35), ("<", 0)])
def test_char_value(char: str, expected: int) -> None:
    assert char_value(char) == expected


@pytest.mark.parametrize("char", ["a", "é", " ", "-", "AB", ""])
def test_char_value_rejects_non_mrz(char: str) -> None:
    with pytest.raises(ValueError):
        char_value(char)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # Exemples ICAO 9303 (spécimens fictifs « Utopia »).
        ("L898902C3", 6),
        ("740812", 2),
        ("120415", 9),
        ("ZE184226B<<<<<", 1),
        ("D23145890", 7),
        ("<<<<<<", 0),
    ],
)
def test_check_digit(data: str, expected: int) -> None:
    assert check_digit(data) == expected


def test_verify() -> None:
    assert verify("740812", "2")
    assert not verify("740812", "3")
    assert not verify("740812", "A")


def test_filler_check_digit_only_for_empty_field() -> None:
    assert verify("<<<<<<<<<<<<<<", "<")
    assert not verify("ZE184226B<<<<<", "<")
