import numpy as np
import pytest

from inference.ocr.text_engine import crop_quad


def test_crop_quad_straightens_a_tilted_line() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    image[50:80, 40:240] = 255  # ligne blanche horizontale
    quad = np.array([[40, 50], [240, 50], [240, 80], [40, 80]], dtype=np.float32)
    line = crop_quad(image, quad)
    assert line.shape[:2] == (30, 200)
    assert line.mean() == pytest.approx(255, abs=5)


def test_vertical_text_is_turned() -> None:
    image = np.zeros((300, 100, 3), dtype=np.uint8)
    quad = np.array([[10, 10], [40, 10], [40, 210], [10, 210]], dtype=np.float32)
    line = crop_quad(image, quad)
    assert line.shape[1] > line.shape[0]
