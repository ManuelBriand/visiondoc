from collections.abc import Sequence

import numpy as np
import pytest
from cv2.typing import MatLike

from inference.ocr.mrz_reader import clean_text, expected_length, prepare_line, read_lines


class ScriptedRecognizer:
    """Renvoie des transcriptions fixées, et note la largeur des images reçues."""

    def __init__(self, *outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.widths: list[list[int]] = []

    def recognize(self, images: Sequence[MatLike]) -> list[str]:
        self.widths.append([image.shape[1] for image in images])
        return self.outputs.pop(0)


def _line(width: int, height: int = 30) -> MatLike:
    line = np.full((height, width), 230, dtype=np.uint8)
    line[5:25:2, ::7] = 20
    return line


@pytest.mark.parametrize(
    ("text", "length", "expected"),
    [
        ("P<FRAMARTIN<<CAMILLE<<<<", 30, "P<FRAMARTIN<<CAMILLE<<<<<<<<<<"),
        ("idfra x4rtbpfw46<<<", 19, "IDFRAX4RTBPFW46<<<<"),
        ("|IDFRA<<|", 7, "IDFRA<<"),
        ("ABC«DEF", 8, "ABC<<DEF"),
        ("ABC<<<<<<<", 6, "ABC<<<"),
        ("ABCDEFG", 6, "ABCDEFG"),  # trop long et pas de remplissage : on ne touche à rien
    ],
)
def test_clean_text(text: str, length: int, expected: str) -> None:
    assert clean_text(text, length) == expected


def test_expected_length() -> None:
    assert expected_length(3, _line(900)) == 30
    assert expected_length(2, _line(1320)) == 44
    assert expected_length(2, _line(1050)) == 36


def test_prepare_line_has_fixed_pitch() -> None:
    prepared = prepare_line(_line(1000), 44)
    assert prepared.shape[0] == 48
    assert prepared.shape[2] == 3
    assert prepared.shape[1] == pytest.approx(44 * 48 * 1.05 + 2 * 19, abs=2)


def test_rereads_when_text_contradicts_line_shape() -> None:
    passport = ["P<FRA" + "<" * 39, "1" * 44]
    recognizer = ScriptedRecognizer(["P<FRA" + "<" * 30, "1" * 44], passport)
    texts = read_lines([_line(1050), _line(1050)], recognizer)
    assert texts == passport
    assert len(recognizer.widths) == 2
    assert recognizer.widths[1][0] > recognizer.widths[0][0]  # relu avec le pas de 44


def test_no_reread_when_shape_and_text_agree() -> None:
    recognizer = ScriptedRecognizer(["A" * 30, "B" * 30, "C" * 30])
    assert read_lines([_line(900)] * 3, recognizer) == ["A" * 30, "B" * 30, "C" * 30]
    assert len(recognizer.widths) == 1
