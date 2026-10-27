from collections.abc import Sequence

from cv2.typing import MatLike

from inference.api.warmup import warm
from inference.ocr.text_engine import TextBox


def test_warm_runs_one_inference_per_model() -> None:
    seen: list[str] = []

    class Recognizer:
        def recognize(self, images: Sequence[MatLike]) -> list[str]:
            seen.append("mrz")
            return [""]

    class Engine:
        def read(self, image: MatLike) -> list[TextBox]:
            seen.append("text")
            return []

    warm(Recognizer(), Engine())
    assert seen == ["mrz", "text"]
