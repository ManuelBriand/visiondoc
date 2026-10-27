"""Polices libres des spécimens synthétiques, téléchargées à la demande et vérifiées par empreinte.

- OCR-B (conversion de Matthew Skala, domaine public) pour la MRZ ;
- Noto Sans (SIL Open Font License) pour la zone visuelle, accents compris.

Elles servent seulement à dessiner des spécimens ; elles ne sont ni commitées ni livrées.
"""

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Font:
    filename: str
    url: str
    sha256: str
    env_override: str


OCRB = _Font(
    filename="ocrb10.ttf",
    url="https://raw.githubusercontent.com/mpdf/mpdf/v8.2.5/ttfonts/ocrb10.ttf",
    sha256="d8eaa9c03541879df82d8fea466278dcc82eaed1881b67a4efb4ff13e946582e",
    env_override="VISIONDOC_OCRB_FONT",
)
NOTO_SANS = _Font(
    filename="NotoSans.ttf",
    url=(
        "https://raw.githubusercontent.com/google/fonts/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5"
        "/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf"
    ),
    sha256="bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d",
    env_override="VISIONDOC_TEXT_FONT",
)


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "visiondoc"


def _font_path(font: _Font) -> Path:
    override = os.environ.get(font.env_override)
    if override:
        return Path(override)
    path = _cache_dir() / font.filename
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == font.sha256:
        return path
    with urllib.request.urlopen(font.url, timeout=60) as response:  # noqa: S310 - URL https figée
        data: bytes = response.read()
    if hashlib.sha256(data).hexdigest() != font.sha256:
        raise RuntimeError(f"Empreinte inattendue pour la police {font.filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def ocrb_font_path() -> Path:
    return _font_path(OCRB)


def text_font_path() -> Path:
    return _font_path(NOTO_SANS)
