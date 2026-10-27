"""Rendu de documents factices à plat, faces et MRZ, puis simulation d'une photo de téléphone.

Mise en page générique inspirée des documents français (libellés, formats de date), sans
aucun élément de sécurité : ce ne sont pas des reproductions de documents réels.
"""

import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from cv2.typing import MatLike
from PIL import Image, ImageDraw, ImageFont

from inference.mrz.generator import MrzIdentity, build_fr_legacy, build_td1, build_td3
from inference.mrz.models import Sex

DocumentKind = Literal["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"]

# Dimensions à 300 dpi (≈ 11,81 px/mm) : carte ID-1 (85,6 x 54 mm), page passeport (125 x 88 mm).
_SIZES: dict[DocumentKind, tuple[int, int]] = {
    "fr_id_card_2021": (1011, 638),
    "fr_id_card_legacy": (1011, 638),
    "fr_passport": (1476, 1039),
}
_MRZ_PITCH_PX = 30  # 2,54 mm par caractère (ICAO)
_OCRB_ADVANCE_EM = 0.72
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"

_LAST_NAMES = (
    "Martin", "Bernard", "Lefèvre", "Dupont", "Moreau", "Laurent", "Girard", "Bonnet",
    "De La Fontaine", "Rousseau", "Mercier", "Guérin", "Muller", "Faure", "André",
    "Chevalier", "Gauthier", "Perrin", "N'Diaye", "Le Goff", "Hoarau", "Benoît",
)  # fmt: skip
_FIRST_NAMES = (
    "Camille", "Élodie", "Gaëlle", "Jérôme", "Hélène", "Noémie", "François", "Zoé",
    "Inès", "Léa", "Théo", "Chloé", "Raphaël", "Maëlle", "Jean-Pierre", "Marie",
    "Louis", "Anaïs", "Clément", "Odile", "Yannick", "Bérénice", "Joël", "Aurélien",
)  # fmt: skip
_PLACES = (
    "LYON", "SAINT-ÉTIENNE", "ORLÉANS", "BREST", "NÎMES", "BÉZIERS", "AIX-EN-PROVENCE",
    "PARIS", "MARSEILLE", "LILLE", "CRÉTEIL", "VALENCE", "ANGOULÊME", "SÈTE", "ÉVREUX",
    "POINTE-À-PITRE", "SAINT-DENIS", "QUIMPER", "CHÂLONS-EN-CHAMPAGNE",
)  # fmt: skip


@dataclass(frozen=True)
class Fonts:
    mrz: Path  # OCR-B
    text: Path  # police latine avec accents


@dataclass(frozen=True)
class Capture:
    """Conditions de prise de vue simulées."""

    blur_sigma: float = 0.0
    upside_down: bool = False
    angle: float | None = None  # degrés ; None : tirage entre -10° et +10°
    brightness: float = 1.0  # multiplie l'éclairage (0,4 : pièce sombre ; 1,5 : surexposé)
    jpeg_quality: int | None = None  # None : tirage entre 80 et 92
    width: int = 1600  # largeur de la photo en pixels
    shift: tuple[float, float] = (0.0, 0.0)  # décalage, en fraction de l'image (photo coupée)


@dataclass(frozen=True)
class Specimen:
    kind: DocumentKind
    identity: MrzIdentity  # noms tels qu'imprimés (accents compris)
    mrz: tuple[str, ...]
    image: bytes  # face portant la MRZ (JPEG)
    other_image: bytes | None  # autre face, s'il y en a une
    birth_place: str
    issue_date: date
    printed_expiry: date  # date de fin de validité imprimée
    capture: Capture


@dataclass(frozen=True)
class _Text:
    x: float  # fractions de la largeur et de la hauteur
    y: float
    text: str
    role: Literal["label", "value", "title"]


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 février
        return value.replace(year=value.year + years, day=28)


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


@dataclass(frozen=True)
class _Draft:
    identity: MrzIdentity
    birth_place: str
    issue_date: date
    printed_expiry: date


def _draft(rng: random.Random, kind: DocumentKind) -> _Draft:
    first_names = tuple(rng.sample(_FIRST_NAMES, rng.randint(1, 3)))
    last_name = rng.choice(_LAST_NAMES)
    # Ancienne CNI délivrée jusqu'en mars 2021, ici à 15 ans au plus tôt.
    latest_birth = date(2005, 12, 31) if kind == "fr_id_card_legacy" else date(2006, 12, 31)
    birth = _random_date(rng, date(1940, 1, 1), latest_birth)
    sex: Sex = "M" if rng.random() < 0.5 else "F"
    if kind == "fr_id_card_legacy":
        issue = _random_date(rng, max(date(1996, 1, 1), _add_years(birth, 15)), date(2021, 3, 1))
        office = "".join(rng.choice(_DIGITS) for _ in range(3))
        number = issue.strftime("%y%m") + office + "".join(rng.choice(_DIGITS) for _ in range(5))
        optional = office + "".join(rng.choice(_DIGITS) for _ in range(3))
        expiry = None
    elif kind == "fr_passport":
        issue = _random_date(rng, date(2012, 1, 1), date(2026, 9, 30))
        number = (
            "".join(rng.choice(_DIGITS) for _ in range(2))
            + "".join(rng.choice(_LETTERS) for _ in range(2))
            + "".join(rng.choice(_DIGITS) for _ in range(5))
        )
        optional, expiry = "", _add_years(issue, 10)
    else:
        issue = _random_date(rng, date(2021, 8, 2), date(2026, 9, 30))
        number = "".join(rng.choice(_LETTERS + _DIGITS) for _ in range(9))
        optional, expiry = "", _add_years(issue, 10)
    identity = MrzIdentity(
        last_name=last_name,
        first_names=first_names,
        document_number=number,
        birth_date=birth,
        sex=sex,
        expiry_date=expiry,
        optional_data=optional,
    )
    return _Draft(
        identity=identity,
        birth_place=rng.choice(_PLACES),
        issue_date=issue,
        printed_expiry=expiry or _add_years(issue, 10),
    )


def random_identity(rng: random.Random, kind: DocumentKind) -> MrzIdentity:
    return _draft(rng, kind).identity


def mrz_lines(kind: DocumentKind, identity: MrzIdentity) -> tuple[str, ...]:
    if kind == "fr_id_card_2021":
        return build_td1(identity)
    if kind == "fr_passport":
        return build_td3(identity)
    return build_fr_legacy(identity)


def _spaced(value: date) -> str:
    return value.strftime("%d %m %Y")


def _dotted(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _layout(kind: DocumentKind, side: Literal["mrz", "other"], draft: _Draft) -> list[_Text]:
    """Libellés et valeurs de chaque face, en coordonnées relatives."""
    who = draft.identity
    given = ", ".join(who.first_names)
    sex = who.sex or "X"
    if kind == "fr_id_card_2021":
        if side == "other":  # recto
            return [
                _Text(0.33, 0.05, "RÉPUBLIQUE FRANÇAISE", "title"),
                _Text(0.33, 0.12, "CARTE NATIONALE D'IDENTITÉ / IDENTITY CARD", "title"),
                _Text(0.35, 0.20, "NOM / Surname", "label"),
                _Text(0.35, 0.25, who.last_name.upper(), "value"),
                _Text(0.35, 0.33, "Prénoms / Given names", "label"),
                _Text(0.35, 0.38, given, "value"),
                _Text(0.35, 0.46, "SEXE / Sex", "label"),
                _Text(0.35, 0.51, sex, "value"),
                _Text(0.66, 0.46, "NATIONALITÉ / Nationality", "label"),
                _Text(0.66, 0.51, "FRA", "value"),
                _Text(0.35, 0.59, "DATE DE NAISS. / Date of birth", "label"),
                _Text(0.35, 0.64, _spaced(who.birth_date), "value"),
                _Text(0.66, 0.59, "LIEU DE NAISSANCE / Place of birth", "label"),
                _Text(0.66, 0.64, draft.birth_place, "value"),
                _Text(0.05, 0.75, "N° DU DOCUMENT / Document No", "label"),
                _Text(0.05, 0.80, who.document_number, "value"),
                _Text(0.66, 0.75, "DATE D'EXPIR. / Expiry date", "label"),
                _Text(0.66, 0.80, _spaced(draft.printed_expiry), "value"),
            ]
        return [  # verso, avec la MRZ
            _Text(0.05, 0.06, "ADRESSE / Address", "label"),
            _Text(0.05, 0.12, "12 RUE DES LILAS 69003 LYON", "value"),
            _Text(0.05, 0.24, "DATE DE DÉLIVRANCE / Date of issue", "label"),
            _Text(0.05, 0.30, _spaced(draft.issue_date), "value"),
        ]
    if kind == "fr_id_card_legacy":
        if side == "mrz":  # recto
            return [
                _Text(0.05, 0.04, "RÉPUBLIQUE FRANÇAISE", "title"),
                _Text(
                    0.33, 0.12, f"CARTE NATIONALE D'IDENTITÉ N° : {who.document_number}", "title"
                ),
                _Text(0.33, 0.24, f"Nom : {who.last_name.upper()}", "value"),
                _Text(0.33, 0.33, f"Prénom(s) : {given}", "value"),
                _Text(0.33, 0.42, f"Sexe : {sex}", "value"),
                _Text(0.33, 0.51, f"Né(e) le : {_dotted(who.birth_date)}", "value"),
                _Text(0.33, 0.60, f"à : {draft.birth_place}", "value"),
                _Text(0.66, 0.42, "Taille : 1,72 m", "value"),
            ]
        return [  # verso
            _Text(0.05, 0.10, "Adresse : 4 PLACE DU MARCHÉ 29000 QUIMPER", "value"),
            _Text(0.05, 0.30, f"Carte valable jusqu'au : {_dotted(draft.printed_expiry)}", "value"),
            _Text(0.05, 0.42, f"délivrée le : {_dotted(draft.issue_date)}", "value"),
            _Text(0.05, 0.54, "par : PRÉFECTURE DU FINISTÈRE", "value"),
        ]
    return [  # page de données du passeport
        _Text(0.35, 0.04, "RÉPUBLIQUE FRANÇAISE   PASSEPORT / PASSPORT", "title"),
        _Text(0.35, 0.12, "Type / Type", "label"),
        _Text(0.35, 0.16, "P", "value"),
        _Text(0.50, 0.12, "Code du pays / Country code", "label"),
        _Text(0.50, 0.16, "FRA", "value"),
        _Text(0.72, 0.12, "Passeport n° / Passport No.", "label"),
        _Text(0.72, 0.16, who.document_number, "value"),
        _Text(0.35, 0.23, "Nom / Surname", "label"),
        _Text(0.35, 0.27, who.last_name.upper(), "value"),
        _Text(0.35, 0.34, "Prénoms / Given names", "label"),
        _Text(0.35, 0.38, given, "value"),
        _Text(0.35, 0.45, "Nationalité / Nationality", "label"),
        _Text(0.35, 0.49, "Française", "value"),
        _Text(0.35, 0.56, "Date de naissance / Date of birth", "label"),
        _Text(0.35, 0.60, _spaced(who.birth_date), "value"),
        _Text(0.65, 0.56, "Lieu de naissance / Place of birth", "label"),
        _Text(0.65, 0.60, draft.birth_place, "value"),
        _Text(0.35, 0.67, "Sexe / Sex", "label"),
        _Text(0.35, 0.71, sex, "value"),
        _Text(0.50, 0.67, "Date de délivrance / Date of issue", "label"),
        _Text(0.50, 0.71, _spaced(draft.issue_date), "value"),
        _Text(0.75, 0.67, "Date d'expiration / Date of expiry", "label"),
        _Text(0.75, 0.71, _spaced(draft.printed_expiry), "value"),
    ]


def _background(width: int, height: int, rng: random.Random) -> tuple[Image.Image, list[int]]:
    tint = [rng.randint(215, 245) for _ in range(3)]
    canvas = Image.new("RGB", (width, height), (tint[0], tint[1], tint[2]))
    draw = ImageDraw.Draw(canvas)
    # Guilloches légères, comme l'impression de sécurité.
    for _ in range(40):
        y0 = rng.randint(0, height)
        amp, period = rng.randint(5, 30), rng.randint(80, 300)
        color = tuple(max(0, c - rng.randint(10, 35)) for c in tint)
        points = [(x, y0 + amp * np.sin(2 * np.pi * x / period)) for x in range(0, width, 8)]
        draw.line(points, fill=color, width=1)
    return canvas, tint


def _draw_mrz(
    draw: ImageDraw.ImageDraw, lines: tuple[str, ...], font: Path, size: tuple[int, int]
) -> None:
    width, height = size
    pitch = min(_MRZ_PITCH_PX, (width - 60) // len(lines[0]))
    mrz_font = ImageFont.truetype(str(font), round(pitch / _OCRB_ADVANCE_EM))
    line_height = round(pitch * 1.65)
    left = (width - pitch * len(lines[0])) // 2
    top = height - round(height * 0.05) - line_height * len(lines)
    for index, line in enumerate(lines):
        for col, char in enumerate(line):
            draw.text((left + col * pitch, top + index * line_height), char, font=mrz_font, fill=0)


def render_side(
    kind: DocumentKind,
    texts: list[_Text],
    fonts: Fonts,
    rng: random.Random,
    mrz: tuple[str, ...] = (),
    photo: bool = True,
) -> MatLike:
    width, height = _SIZES[kind]
    canvas, _ = _background(width, height, rng)
    draw = ImageDraw.Draw(canvas)
    if photo:
        draw.rectangle(
            (round(width * 0.04), round(height * 0.18), round(width * 0.29), round(height * 0.62)),
            fill=(150, 150, 155),
        )
    sizes = {"label": 0.030, "value": 0.046, "title": 0.034}
    colors = {"label": (70, 70, 110), "value": (20, 20, 35), "title": (40, 40, 120)}
    # Même résolution pour tous : corps de texte proches, un peu plus grands sur le passeport.
    base = _SIZES["fr_id_card_2021"][1] * (1.2 if kind == "fr_passport" else 1.0)
    for item in texts:
        size = round(base * sizes[item.role])
        font = ImageFont.truetype(str(fonts.text), size)
        room = width * (0.97 - item.x)
        while font.getlength(item.text) > room and size > 10:
            size -= 1  # comme sur un vrai document, un texte long est imprimé plus petit
            font = ImageFont.truetype(str(fonts.text), size)
        draw.text((item.x * width, item.y * height), item.text, font=font, fill=colors[item.role])
    if mrz:
        _draw_mrz(draw, mrz, fonts.mrz, (width, height))
    rgb = np.asarray(canvas)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def render_document(
    kind: DocumentKind, lines: tuple[str, ...], fonts: Fonts, rng: random.Random
) -> MatLike:
    """Face portant la MRZ, avec un faux contenu visuel (pour les tests de vision)."""
    return render_side(kind, _layout(kind, "mrz", _draft(rng, kind)), fonts, rng, mrz=lines)


def photograph(document: MatLike, rng: random.Random, capture: Capture | None = None) -> bytes:
    """Pose le document sur un fond, avec perspective, éclairage, bruit, flou et JPEG.

    Le document reste entièrement dans le cadre, sauf décalage explicite (`capture.shift`)
    pour simuler une photo coupée.
    """
    capture = capture or Capture()
    out_width, shift = capture.width, capture.shift
    doc_h, doc_w = document.shape[:2]
    out_height = round(out_width * 0.75)
    background = np.full((out_height, out_width, 3), rng.randint(30, 110), dtype=np.float32)
    background += (
        np.random.default_rng(rng.randint(0, 2**32))
        .normal(0, 12, background.shape)
        .astype(np.float32)
    )

    scale = rng.uniform(0.6, 0.8) * out_width / doc_w
    tilt = capture.angle if capture.angle is not None else rng.uniform(-10, 10)
    cx = out_width * (0.5 + shift[0]) + rng.uniform(-60, 60)
    cy = out_height * (0.5 + shift[1]) + rng.uniform(-40, 40)
    angle = np.deg2rad(tilt + (180 if capture.upside_down else 0))
    half = np.array([[-doc_w, -doc_h], [doc_w, -doc_h], [doc_w, doc_h], [-doc_w, doc_h]]) / 2
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    offsets = (half @ rotation.T) * scale
    offsets += np.array([[rng.uniform(-1, 1) for _ in range(2)] for _ in range(4)]) * (
        rng.uniform(0.0, 0.05) * doc_w * scale
    )
    if shift == (0.0, 0.0):
        # Réduit l'échelle jusqu'à ce que le document tienne dans le cadre, avec une marge.
        margin = 0.03 * out_width
        reach_x = (out_width / 2 - margin - abs(cx - out_width / 2)) / np.abs(offsets[:, 0]).max()
        reach_y = (out_height / 2 - margin - abs(cy - out_height / 2)) / np.abs(offsets[:, 1]).max()
        offsets *= min(1.0, reach_x, reach_y)
    corners = offsets + np.array([cx, cy])

    source = np.array([[0, 0], [doc_w, 0], [doc_w, doc_h], [0, doc_h]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(source, corners.astype(np.float32))
    warped = cv2.warpPerspective(document, matrix, (out_width, out_height))
    mask = cv2.warpPerspective(
        np.full((doc_h, doc_w), 255, dtype=np.uint8), matrix, (out_width, out_height)
    )
    scene = np.where(mask[:, :, None] > 0, warped.astype(np.float32), background)

    gradient = capture.brightness * np.linspace(
        rng.uniform(0.75, 1.0), rng.uniform(0.95, 1.1), out_width
    )
    scene *= gradient[None, :, None]
    scene += np.random.default_rng(rng.randint(0, 2**32)).normal(0, 3, scene.shape)
    image: MatLike = np.clip(scene, 0, 255).astype(np.uint8)
    if capture.blur_sigma > 0:
        image = cv2.GaussianBlur(image, (0, 0), capture.blur_sigma)
    quality = capture.jpeg_quality or rng.randint(80, 92)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("Encodage JPEG impossible")
    return encoded.tobytes()


def make_specimen(
    kind: DocumentKind,
    rng: random.Random,
    fonts: Fonts,
    capture: Capture | None = None,
) -> Specimen:
    capture = capture or Capture()
    draft = _draft(rng, kind)
    lines = mrz_lines(kind, draft.identity)
    mrz_side = render_side(
        kind, _layout(kind, "mrz", draft), fonts, rng, mrz=lines, photo=kind != "fr_id_card_2021"
    )
    image = photograph(mrz_side, rng, capture)
    other_image = None
    if kind != "fr_passport":
        other_side = render_side(
            kind, _layout(kind, "other", draft), fonts, rng, photo=kind == "fr_id_card_2021"
        )
        # L'autre face est photographiée dans les mêmes conditions, mais à l'endroit.
        other_image = photograph(other_side, rng, replace(capture, upside_down=False))
    return Specimen(
        kind=kind,
        identity=draft.identity,
        mrz=lines,
        image=image,
        other_image=other_image,
        birth_place=draft.birth_place,
        issue_date=draft.issue_date,
        printed_expiry=draft.printed_expiry,
        capture=capture,
    )
