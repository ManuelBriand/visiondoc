"""Lecture des champs texte : noms, sexe, codes pays."""

import re

from inference.mrz.errors import MrzError
from inference.mrz.models import Sex

_FILLER_RUN = re.compile(r"<+")


def _require_letters(field: str) -> None:
    if not all("A" <= c <= "Z" or c == "<" for c in field):
        raise MrzError("invalid_field", "Nom illisible dans la MRZ")


def strip_filler(field: str) -> str:
    """`DE<LA<FONTAINE<<<` → `DE LA FONTAINE`."""
    return _FILLER_RUN.sub(" ", field).strip()


def parse_surname(field: str) -> str:
    _require_letters(field)
    return strip_filler(field)


def parse_icao_name(field: str) -> tuple[str, tuple[str, ...]]:
    """Champ nom ICAO : nom, `<<`, prénoms séparés par `<`."""
    _require_letters(field)
    primary, _, secondary = field.rstrip("<").partition("<<")
    first_names = tuple(name for name in secondary.split("<") if name)
    return strip_filler(primary), first_names


def parse_legacy_given_names(field: str) -> tuple[str, ...]:
    """Ancienne CNI : prénoms séparés par `<<`, `<` simple à l'intérieur d'un prénom composé."""
    _require_letters(field)
    parts = (strip_filler(part) for part in field.rstrip("<").split("<<"))
    return tuple(part for part in parts if part)


def parse_sex(char: str) -> Sex | None:
    if char == "M":
        return "M"
    if char == "F":
        return "F"
    if char in ("<", "X"):
        return None
    raise MrzError("invalid_field", "Sexe illisible dans la MRZ")


def parse_country(field: str) -> str:
    if not all("A" <= c <= "Z" or c == "<" for c in field):
        raise MrzError("invalid_field", "Code pays illisible dans la MRZ")
    return field.replace("<", "")
