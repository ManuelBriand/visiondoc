import io

import numpy as np
import pytest
from PIL import Image

from inference.errors import ExtractionError
from inference.vision.file_check import MAX_FILE_BYTES, load_image, sniff


def _encode(img: Image.Image, fmt: str, **kwargs: object) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def _code(data: bytes) -> str:
    with pytest.raises(ExtractionError) as excinfo:
        load_image(data)
    return excinfo.value.code


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_decodes_raster_to_bgr(fmt: str) -> None:
    img = Image.new("RGB", (40, 20), (255, 0, 0))
    decoded = load_image(_encode(img, fmt))
    assert decoded.shape == (20, 40, 3)
    blue, green, red = decoded[10, 20]
    assert red > 200 and blue < 50 and green < 50


def test_exif_orientation_is_applied() -> None:
    img = Image.new("RGB", (40, 20))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotation de 90° à appliquer
    decoded = load_image(_encode(img, "JPEG", exif=exif))
    assert decoded.shape[:2] == (40, 20)


def test_type_comes_from_signature_not_extension() -> None:
    assert sniff(_encode(Image.new("RGB", (4, 4)), "PNG")) == "png"
    assert _code(b"GIF89a" + b"\x00" * 100) == "invalid_format"
    assert _code(b"just some text") == "invalid_format"


def test_too_large() -> None:
    assert _code(b"\xff\xd8\xff" + b"\x00" * MAX_FILE_BYTES) == "file_too_large"


def test_corrupted_jpeg() -> None:
    assert _code(b"\xff\xd8\xff\xe0" + b"\x13" * 500) == "invalid_format"


def test_decompression_bomb_rejected_before_decoding() -> None:
    # 10 000 x 5 000 px en noir et blanc : quelques Ko compressés, 50 Mpx une fois décodés.
    bomb = _encode(Image.new("1", (10_000, 5_000)), "PNG")
    assert len(bomb) < 200_000
    assert _code(bomb) == "invalid_format"


def test_single_page_pdf_is_rendered() -> None:
    page = Image.new("RGB", (200, 100), (0, 0, 255))
    rendered = load_image(_encode(page, "PDF", resolution=72))
    assert rendered.ndim == 3 and rendered.shape[2] == 3
    assert rendered.shape[1] > rendered.shape[0]
    blue, _, red = np.asarray(rendered[rendered.shape[0] // 2, rendered.shape[1] // 2], dtype=int)
    assert blue > 200 and red < 50


def test_multi_page_pdf_rejected() -> None:
    pages = [Image.new("RGB", (100, 100)) for _ in range(2)]
    data = _encode(pages[0], "PDF", save_all=True, append_images=pages[1:])
    assert _code(data) == "invalid_format"


def test_malformed_pdf_rejected() -> None:
    assert _code(b"%PDF-1.7\n" + b"garbage" * 50) == "invalid_format"
