"""Toute substitution d'un caractère dans une zone couverte par une clé est détectée.

Limite inhérente à l'algorithme ICAO 7-3-1 : deux caractères dont les valeurs diffèrent
d'un multiple de 10 (`A`/`0`, `K`/`A`, `<`/`0`…) donnent la même clé. Dans les champs
numériques et alphabétiques, la normalisation et la validation syntaxique réduisent cette
brèche ; elle subsiste entre lettres d'un nom (`A`/`K`/`U`) et dans les champs
alphanumériques (numéro de document, données optionnelles).
"""

from collections.abc import Iterator
from datetime import date

import pytest

from inference.mrz import MrzError, MrzResult, parse_mrz
from inference.mrz.checksum import char_value
from inference.mrz.generator import MrzIdentity, build_fr_legacy, build_td1, build_td3
from inference.mrz.normalize import TO_LETTER
from inference.mrz.parser import _ALPHABET

TODAY = date(2026, 10, 22)

IDENTITY = MrzIdentity(
    last_name="Martin",
    first_names=("Camille", "Marie"),
    document_number="X4RTBPFW4",
    birth_date=date(1990, 4, 12),
    sex="F",
    expiry_date=date(2031, 6, 30),
    optional_data="AB12",
)

LEGACY_IDENTITY = MrzIdentity(
    last_name="Martin",
    first_names=("Camille", "Marie"),
    document_number="880692310285",
    birth_date=date(1990, 4, 12),
    sex="F",
    optional_data="921031",
)


def _span(line: int, start: int, end: int) -> list[tuple[int, int]]:
    return [(line, col) for col in range(start, end)]


# (lignes, positions couvertes par une clé, positions numériques, positions alphabétiques)
CASES = {
    "TD1": (
        build_td1(IDENTITY),
        _span(0, 5, 30) + _span(1, 0, 7) + _span(1, 8, 15) + _span(1, 18, 30),
        _span(0, 14, 15) + _span(1, 0, 7) + _span(1, 8, 15) + _span(1, 29, 30),
        [],
    ),
    "TD3": (
        build_td3(IDENTITY),
        _span(1, 0, 10) + _span(1, 13, 20) + _span(1, 21, 44),
        _span(1, 9, 10) + _span(1, 13, 20) + _span(1, 21, 28) + _span(1, 42, 44),
        [],
    ),
    "FR_LEGACY": (
        build_fr_legacy(LEGACY_IDENTITY),
        _span(0, 0, 36) + _span(1, 0, 36),
        _span(1, 12, 13) + _span(1, 27, 34) + _span(1, 35, 36),
        _span(0, 5, 30) + _span(1, 13, 27),
    ),
}


def _identity(result: MrzResult) -> dict[str, object]:
    return result.model_dump(exclude={"raw", "corrections"})


def _mutations(
    lines: tuple[str, ...], positions: list[tuple[int, int]]
) -> Iterator[tuple[int, int, str, list[str]]]:
    for line, col in positions:
        for char in sorted(_ALPHABET - {lines[line][col]}):
            mutated = list(lines)
            mutated[line] = lines[line][:col] + char + lines[line][col + 1 :]
            yield line, col, char, mutated


@pytest.mark.parametrize("name", CASES)
def test_every_single_substitution_is_detected(name: str) -> None:
    lines, covered, numeric, alphabetic = CASES[name]
    original = parse_mrz(lines, today=TODAY)
    assert original.checksums_valid

    for line, col, char, mutated in _mutations(lines, covered):
        try:
            result = parse_mrz(mutated, today=TODAY)
        except MrzError:
            continue
        if not result.checksums_valid:
            continue
        if _identity(result) == _identity(original):
            continue  # confusion OCR corrigée, valeur identique
        assert (line, col) not in numeric, f"{name} non détecté en {line}:{col}"
        if (line, col) in alphabetic:
            char = TO_LETTER.get(char, char)
        delta = char_value(lines[line][col]) - char_value(char)
        assert delta % 10 == 0, f"{name} non détecté en {line}:{col}"
