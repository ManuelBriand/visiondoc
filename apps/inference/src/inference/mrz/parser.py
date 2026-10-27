"""Point d'entrée : détection du format puis lecture de la MRZ."""

from collections.abc import Callable, Sequence
from datetime import date

from inference.mrz import fr_legacy, td1, td3
from inference.mrz.errors import MrzError
from inference.mrz.models import MrzFormat, MrzResult
from inference.mrz.normalize import TO_DIGIT, TO_LETTER, Span, normalize

_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")

Spans = tuple[Span, ...]
ParseFn = Callable[[tuple[str, ...], date], MrzResult]

# Format → (plages numériques, plages alphabétiques, lecteur)
_FORMATS: dict[MrzFormat, tuple[Spans, Spans, ParseFn]] = {
    MrzFormat.TD1: (td1.DIGIT_SPANS, td1.LETTER_SPANS, td1.parse),
    MrzFormat.TD3: (td3.DIGIT_SPANS, td3.LETTER_SPANS, td3.parse),
    MrzFormat.FR_LEGACY: (fr_legacy.DIGIT_SPANS, fr_legacy.LETTER_SPANS, fr_legacy.parse),
}


def detect_format(lines: tuple[str, ...]) -> MrzFormat:
    shape = tuple(len(line) for line in lines)
    if shape == (30, 30, 30):
        return MrzFormat.TD1
    if shape == (44, 44):
        return MrzFormat.TD3
    if shape == (36, 36):
        if lines[0].startswith(fr_legacy.PREFIX):
            return MrzFormat.FR_LEGACY
        raise MrzError("unsupported_format", "MRZ de 36 caractères qui n'est pas une CNI française")
    raise MrzError("invalid_length", "Nombre ou longueur des lignes MRZ invalide")


def parse_mrz(lines: Sequence[str], *, today: date | None = None) -> MrzResult:
    """Lit une MRZ déjà transcrite en texte.

    `today` sert de référence pour le siècle des dates ; il est fixé dans les tests.
    """
    cleaned = tuple(line.strip().upper() for line in lines if line.strip())
    if any(c not in _ALPHABET for line in cleaned for c in line):
        raise MrzError("invalid_characters", "La MRZ contient des caractères non autorisés")
    digit_spans, letter_spans, parse = _FORMATS[detect_format(cleaned)]
    normalized, digit_fixes = normalize(cleaned, digit_spans, TO_DIGIT)
    normalized, letter_fixes = normalize(normalized, letter_spans, TO_LETTER)
    result = parse(normalized, today or date.today())
    corrections = tuple(sorted(digit_fixes + letter_fixes))
    return result.model_copy(update={"raw": cleaned, "corrections": corrections})
