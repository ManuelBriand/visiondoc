"""Normalisation de texte commune : majuscules, sans accents."""

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_NON_NAME = re.compile(r"[^A-Z ]+")
_SPACES = re.compile(r"\s+")


def fold(text: str) -> str:
    """Majuscules sans diacritiques : « Élodie » → « ELODIE »."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def normalize_label(text: str) -> str:
    """Forme de comparaison des libellés : « N° DU DOCUMENT » → « N DU DOCUMENT »."""
    return _NON_ALNUM.sub(" ", fold(text)).strip()


def normalize_name(text: str) -> str:
    """Noms : tirets et apostrophes deviennent des espaces, comme dans la MRZ."""
    return _SPACES.sub(" ", _NON_NAME.sub(" ", fold(text).replace("-", " "))).strip()


def compact(text: str) -> str:
    """Comparaison insensible aux espaces : « DE LA FONTAINE » → « DELAFONTAINE »."""
    return normalize_name(text).replace(" ", "")
