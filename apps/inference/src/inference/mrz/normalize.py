"""Correction des confusions OCR courantes, dans les champs dont la nature est certaine.

Un champ strictement numérique (date, clé) ne contient jamais de lettre ; un nom ou un code
pays ne contient jamais de chiffre. Les champs alphanumériques ne sont jamais corrigés.
"""

# (ligne, début, fin) : plage de colonnes d'un même type de caractères.
Span = tuple[int, int, int]

TO_DIGIT = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "B": "8",
}

TO_LETTER = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "6": "G",
    "8": "B",
}


def normalize(
    lines: tuple[str, ...], spans: tuple[Span, ...], mapping: dict[str, str]
) -> tuple[tuple[str, ...], tuple[tuple[int, int], ...]]:
    chars = [list(line) for line in lines]
    corrections: list[tuple[int, int]] = []
    for line, start, end in spans:
        for col in range(start, end):
            replacement = mapping.get(chars[line][col])
            if replacement is not None:
                chars[line][col] = replacement
                corrections.append((line, col))
    return tuple("".join(line) for line in chars), tuple(corrections)
