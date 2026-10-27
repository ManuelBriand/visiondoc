import numpy as np
import pytest

from inference.vision.document import _order_corners


def _rect(cx: float, cy: float, w: float, h: float, degrees: float) -> np.ndarray:
    half = np.array([[-w, -h], [w, -h], [w, h], [-w, h]]) / 2
    a = np.deg2rad(degrees)
    rotation = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return np.asarray(half @ rotation.T + [cx, cy], dtype=np.float64)


@pytest.mark.parametrize("degrees", [0, 10, 44, 45, 46, 80, 90, 135, 180, -30])
def test_first_edge_is_a_long_edge(degrees: float) -> None:
    corners = _rect(500, 400, 300, 190, degrees)
    shuffled = corners[[2, 0, 3, 1]]
    ordered = _order_corners(shuffled)
    top = np.linalg.norm(ordered[1] - ordered[0])
    side = np.linalg.norm(ordered[2] - ordered[1])
    assert top == pytest.approx(300, rel=1e-3)
    assert side == pytest.approx(190, rel=1e-3)


def test_upright_rectangle_starts_top_left() -> None:
    ordered = _order_corners(_rect(500, 400, 300, 190, 0))
    assert ordered[0].tolist() == pytest.approx([350, 305])
    assert ordered[2].tolist() == pytest.approx([650, 495])
