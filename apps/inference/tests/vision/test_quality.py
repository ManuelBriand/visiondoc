import cv2
import numpy as np
import pytest
from cv2.typing import MatLike

from inference.errors import ImageUnreadableError
from inference.vision.quality import ensure_readable, measure


def _textured(seed: int = 0) -> MatLike:
    """Document clair avec des traits nets, comme du texte imprimé."""
    rng = np.random.default_rng(seed)
    image = np.full((760, 1200, 3), 225, dtype=np.uint8)
    for _ in range(400):
        x, y = int(rng.integers(0, 1180)), int(rng.integers(0, 740))
        cv2.rectangle(image, (x, y), (x + 12, y + 18), (30, 30, 30), 2)
    return image


def _cause(image: MatLike, source_width: float = 1200.0) -> str:
    with pytest.raises(ImageUnreadableError) as excinfo:
        ensure_readable(image, source_width)
    return excinfo.value.cause


def test_sharp_document_passes() -> None:
    report = ensure_readable(_textured(), 1200.0)
    assert report.sharpness > 20


def test_blurry() -> None:
    assert _cause(cv2.GaussianBlur(_textured(), (0, 0), 4)) == "blurry"


def test_too_dark() -> None:
    assert _cause((_textured() * 0.08).astype(np.uint8)) == "too_dark"


def test_dim_or_overexposed_photo_is_not_refused_upfront() -> None:
    dim = (_textured() * 0.25).astype(np.uint8)
    bright = _textured()
    bright[:, :1000] = 255
    for image in (dim, bright):
        ensure_readable(image, 1200.0)  # aucune exception : on tente la lecture


def test_likely_cause_explains_a_failed_read() -> None:
    assert measure((_textured() * 0.25).astype(np.uint8)).likely_cause() == "too_dark"
    bright = _textured()
    bright[:, :1000] = 255
    assert measure(bright).likely_cause() == "overexposed"
    soft = cv2.GaussianBlur(_textured(), (0, 0), 1.8)
    assert measure(soft).likely_cause() == "blurry"
    assert measure(_textured()).likely_cause() is None


def test_too_small() -> None:
    assert _cause(_textured(), source_width=300.0) == "too_small"


def test_message_is_actionable_and_in_french() -> None:
    with pytest.raises(ImageUnreadableError) as excinfo:
        ensure_readable(cv2.GaussianBlur(_textured(), (0, 0), 4), 1200.0)
    assert excinfo.value.code == "image_unreadable"
    assert "floue" in excinfo.value.message


def test_measure_is_deterministic() -> None:
    assert measure(_textured(1)) == measure(_textured(1))
