from pathlib import Path

import pytest

from inference.synth.documents import Fonts
from inference.synth.fonts import ocrb_font_path, text_font_path


@pytest.fixture(scope="session")
def ocrb_font() -> Path:
    """Police OCR-B des spécimens synthétiques, téléchargée une fois puis mise en cache."""
    return ocrb_font_path()


@pytest.fixture(scope="session")
def fonts(ocrb_font: Path) -> Fonts:
    return Fonts(mrz=ocrb_font, text=text_font_path())
