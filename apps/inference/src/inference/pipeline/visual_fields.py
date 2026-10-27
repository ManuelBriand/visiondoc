"""Champs de la zone visuelle, repérés par leurs libellés imprimés.

Deux mises en page coexistent : libellé au-dessus de la valeur (nouvelle CNI, passeport)
et « Libellé : valeur » sur une ligne (ancienne CNI). Les libellés sont comparés sous forme
normalisée, avec une tolérance aux erreurs d'OCR pour les libellés longs. Tout libellé
connu, même d'un champ non extrait (adresse, taille…), est marqué pour ne jamais être pris
pour une valeur.

La sortie de l'OCR est une donnée : elle n'est jamais interprétée autrement que comme du
texte à analyser.
"""

import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from inference.ocr.text_engine import TextBox
from inference.text import fold, normalize_label, normalize_name

FieldValue = str | date | tuple[str, ...]

_IGNORED = "_ignored"
_LABELS: dict[str, tuple[str, ...]] = {
    "last_name": ("NOM", "SURNAME"),
    "first_names": ("PRENOMS", "PRENOM S", "PRENOM", "GIVEN NAMES"),
    "sex": ("SEXE", "SEX"),
    "birth_date": (
        "DATE DE NAISSANCE",
        "DATE DE NAISS",
        "DATE OF BIRTH",
        "NE E LE",
        "NEE LE",
        "NE LE",
    ),
    "birth_place": ("LIEU DE NAISSANCE", "PLACE OF BIRTH"),
    "document_number": (
        "CARTE NATIONALE D IDENTITE N",
        "N DU DOCUMENT",
        "DOCUMENT NO",
        "PASSEPORT N",
        "PASSPORT NO",
    ),
    "expiry_date": (
        "CARTE VALABLE JUSQU AU",
        "VALABLE JUSQU AU",
        "DATE D EXPIRATION",
        "DATE D EXPIR",
        "EXPIRY DATE",
        "DATE OF EXPIRY",
    ),
    "issue_date": ("DATE DE DELIVRANCE", "DATE OF ISSUE", "DELIVREE LE"),
    _IGNORED: (
        "NOM D USAGE",
        "ALTERNATE NAME",
        "ADRESSE",
        "ADDRESS",
        "TAILLE",
        "HEIGHT",
        "AUTORITE",
        "AUTHORITY",
        "PAR",
        "TYPE",
        "CODE DU PAYS",
        "COUNTRY CODE",
        "NATIONALITE",
        "NATIONALITY",
        "REPUBLIQUE FRANCAISE",
        "CARTE NATIONALE D IDENTITE",
        "IDENTITY CARD",
        "PASSEPORT",
        "PASSPORT",
        "SIGNATURE",
    ),
}
_VARIANTS = sorted(
    ((variant, field) for field, variants in _LABELS.items() for variant in variants),
    key=lambda item: -len(item[0]),
)
_FUZZY_MIN_LENGTH = 6
_FUZZY_RATIO = 0.85
# Ancienne CNI : « à : LYON », libellé d'une seule lettre, reconnu par sa forme exacte.
_LEGACY_PLACE = re.compile(r"^\s*[aàAÀ]\s*:\s*(.+)$")

_MONTHS = {
    "JANV": 1, "JAN": 1, "FEVR": 2, "FEV": 2, "FEB": 2, "MARS": 3, "MAR": 3, "AVR": 4,
    "APR": 4, "MAI": 5, "MAY": 5, "JUIN": 6, "JUN": 6, "JUIL": 7, "JUL": 7, "AOUT": 8,
    "AUG": 8, "SEPT": 9, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip
_DIGIT_FIXES = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5"})
_NUMERIC_DATE = re.compile(r"(\d{1,2})\D{1,3}(\d{1,2})\D{1,3}(\d{4})")
_NAMED_DATE = re.compile(r"(\d{1,2})\s*([A-Z]{3,5})\.?\s*(\d{4})")


@dataclass(frozen=True)
class VisualValue:
    value: FieldValue
    score: float  # confiance de l'OCR sur la ligne de la valeur


@dataclass(frozen=True)
class _Label:
    field: str
    box: TextBox
    inline: str | None  # valeur sur la même ligne que le libellé


def _match_prefix(text: str, variant: str) -> bool:
    if len(text) < len(variant):
        return False
    if len(text) > len(variant) and text[len(variant)] != " ":
        return False
    head = text[: len(variant)]
    if len(variant) < _FUZZY_MIN_LENGTH:
        return head == variant
    return SequenceMatcher(None, head, variant).ratio() >= _FUZZY_RATIO


def _segment(box: TextBox, start: float, end: float) -> TextBox:
    width = box.x1 - box.x0
    return TextBox(
        box.text, box.score, box.x0 + start * width, box.y0, box.x0 + end * width, box.y1
    )


def _parse_labels(box: TextBox) -> list[_Label]:
    """Libellés d'une ligne. L'OCR fusionne parfois deux libellés voisins (« Date de
    délivrance / Date of issue Date d'expiration / Date of expiry ») : la ligne est alors
    découpée, l'abscisse de chaque libellé étant estimée au prorata des caractères."""
    place = _LEGACY_PLACE.match(box.text)
    if place:
        return [_Label("birth_place", box, place.group(1))]
    text = normalize_label(box.text)
    rest = text
    segments: list[tuple[str, int]] = []  # (champ, position de début dans `text`)
    while rest:
        for variant, candidate in _VARIANTS:
            if _match_prefix(rest, variant):
                position = len(text) - len(rest)
                if not segments or candidate not in (segments[-1][0], _IGNORED):
                    segments.append((candidate, position))
                rest = rest[len(variant) :].strip()
                break
        else:
            break
    if not segments:
        return []
    labels: list[_Label] = []
    for index, (field, start) in enumerate(segments):
        end = segments[index + 1][1] if index + 1 < len(segments) else len(text)
        labels.append(_Label(field, _segment(box, start / len(text), end / len(text)), None))
    if rest:
        # Valeur sur la ligne : on la reprend dans le texte d'origine (accents, virgules).
        inline = box.text.split(":", 1)[1] if ":" in box.text else rest
        labels[-1] = _Label(labels[-1].field, labels[-1].box, inline)
    return labels


def _is_mrz(box: TextBox) -> bool:
    return box.text.count("<") >= 3


def _find_value(label: _Label, candidates: list[TextBox], used: set[int]) -> TextBox | None:
    """Valeur la plus proche sous le libellé, alignée à gauche ; à défaut, à sa droite."""
    height = max(label.box.height, 1.0)
    best: tuple[float, TextBox] | None = None
    for box in candidates:
        if id(box) in used:
            continue
        below = (
            box.center_y > label.box.center_y
            and box.y0 - label.box.y1 < 2.0 * height
            and abs(box.x0 - label.box.x0) < 3.0 * height
        )
        beside = abs(box.center_y - label.box.center_y) < 0.6 * height and box.x0 > label.box.x1
        if below:
            distance = box.y0 - label.box.y1 + abs(box.x0 - label.box.x0) * 0.1
        elif beside:
            distance = box.x0 - label.box.x1 + 3.0 * height
        else:
            continue
        if best is None or distance < best[0]:
            best = (distance, box)
    return best[1] if best else None


def parse_date(text: str) -> date | None:
    folded = fold(text)
    named = _NAMED_DATE.search(folded)
    if named and named.group(2) in _MONTHS:
        day, month, year = int(named.group(1)), _MONTHS[named.group(2)], int(named.group(3))
    else:
        numeric = _NUMERIC_DATE.search(folded.translate(_DIGIT_FIXES))
        if numeric is None:
            return None
        day, month, year = (int(group) for group in numeric.groups())
    if not 1900 <= year <= 2100:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_value(field: str, raw: str) -> FieldValue | None:
    if field in ("birth_date", "expiry_date", "issue_date"):
        return parse_date(raw)
    if field == "sex":
        letters = [c for c in fold(raw) if c in "MF"]
        return letters[0] if letters else None
    if field == "document_number":
        number = re.sub(r"[^A-Z0-9]", "", fold(raw))
        return number if len(number) >= 6 else None
    if field == "first_names":
        parts = raw.split(",") if "," in raw else raw.split()
        names = tuple(name for name in (normalize_name(part) for part in parts) if name)
        return names or None
    if field == "last_name":
        return normalize_name(raw) or None
    if field == "birth_place":
        place = re.sub(r"\s*\(\w+\)\s*$", "", fold(raw)).strip(" :")
        return re.sub(r"\s+", " ", place) or None
    return None


def read_fields(boxes: list[TextBox]) -> dict[str, VisualValue]:
    texts = [box for box in boxes if not _is_mrz(box)]
    labels: list[_Label] = []
    values: list[TextBox] = []
    for box in texts:
        found = _parse_labels(box)
        if found:
            labels.extend(found)
        else:
            values.append(box)

    fields: dict[str, VisualValue] = {}
    used: set[int] = set()
    # Libellés en ligne d'abord, puis les autres de haut en bas.
    for label in sorted(labels, key=lambda lb: (lb.inline is None, lb.box.y0, lb.box.x0)):
        if label.field == _IGNORED or label.field in fields:
            continue
        if label.inline is not None:
            raw, score = label.inline, label.box.score
        else:
            value_box = _find_value(label, values, used)
            if value_box is None:
                continue
            used.add(id(value_box))
            raw, score = value_box.text, value_box.score
        parsed = _parse_value(label.field, raw)
        if parsed is not None:
            fields[label.field] = VisualValue(parsed, score)
    return fields


def count_labels(boxes: list[TextBox]) -> int:
    """Nombre de libellés reconnus : sert à choisir l'orientation d'une face sans MRZ."""
    return sum(len(_parse_labels(box)) for box in boxes)
