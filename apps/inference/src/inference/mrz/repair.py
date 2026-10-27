"""Lecture tolérante : correction des confusions OCR dans les champs alphanumériques.

Un numéro de document mélange lettres et chiffres : `O` et `0` y sont tous deux possibles.
Quand une clé échoue, on essaie les permutations ambiguës sur ces champs ; une correction
n'est retenue que si exactement une variante rend toutes les clés valides.
"""

from collections.abc import Sequence
from datetime import date
from itertools import combinations

from inference.mrz.errors import MrzError
from inference.mrz.fr_legacy import PREFIX as LEGACY_PREFIX
from inference.mrz.models import MrzFormat, MrzResult
from inference.mrz.parser import detect_format, parse_mrz

_SWAPS: dict[str, tuple[str, ...]] = {
    "0": ("O", "D", "Q"),
    "O": ("0",),
    "D": ("0",),
    "Q": ("0",),
    "1": ("I",),
    "I": ("1",),
    "2": ("Z",),
    "Z": ("2",),
    "5": ("S",),
    "S": ("5",),
    "6": ("G",),
    "G": ("6",),
    "8": ("B",),
    "B": ("8",),
}

# Champs alphanumériques couverts par une clé : (ligne, début, fin).
_FIELDS: dict[MrzFormat, tuple[tuple[int, int, int], ...]] = {
    MrzFormat.TD1: ((0, 5, 14), (0, 15, 30), (1, 18, 29)),
    MrzFormat.TD3: ((1, 0, 9), (1, 28, 42)),
    MrzFormat.FR_LEGACY: ((0, 30, 36), (1, 0, 12)),
}
_MAX_SWAPS = 2


def _candidates(
    lines: tuple[str, ...], positions: list[tuple[int, int]], count: int
) -> list[tuple[tuple[str, ...], tuple[tuple[int, int], ...]]]:
    variants: list[tuple[tuple[str, ...], tuple[tuple[int, int], ...]]] = []
    for chosen in combinations(positions, count):
        partial: list[tuple[list[list[str]], tuple[tuple[int, int], ...]]] = [
            ([list(line) for line in lines], chosen)
        ]
        for line, col in chosen:
            partial = [
                (
                    [
                        row if i != line else [*row[:col], alt, *row[col + 1 :]]
                        for i, row in enumerate(grid)
                    ],
                    pos,
                )
                for grid, pos in partial
                for alt in _SWAPS[lines[line][col]]
            ]
        variants.extend((tuple("".join(row) for row in grid), pos) for grid, pos in partial)
    return variants


def restore_fixed_prefix(lines: Sequence[str]) -> tuple[list[str], tuple[tuple[int, int], ...]]:
    """Ancienne CNI : le préfixe `IDFRA` est fixe ; un seul caractère mal lu est restauré."""
    cleaned = [line.strip().upper() for line in lines if line.strip()]
    if [len(line) for line in cleaned] != [36, 36]:
        return cleaned, ()
    head = cleaned[0][:5]
    wrong = [
        col for col, (got, want) in enumerate(zip(head, LEGACY_PREFIX, strict=True)) if got != want
    ]
    if len(wrong) != 1:
        return cleaned, ()
    cleaned[0] = LEGACY_PREFIX + cleaned[0][5:]
    return cleaned, ((0, wrong[0]),)


def parse_mrz_tolerant(lines: Sequence[str], *, today: date | None = None) -> MrzResult:
    """Comme `parse_mrz`, avec correction des ambiguïtés quand une seule variante est valide."""
    restored, prefix_fix = restore_fixed_prefix(lines)
    if prefix_fix:
        result = parse_mrz_tolerant(restored, today=today)
        corrections = tuple(sorted({*result.corrections, *prefix_fix}))
        raw = tuple(line.strip().upper() for line in lines if line.strip())
        return result.model_copy(update={"raw": raw, "corrections": corrections})
    result = parse_mrz(lines, today=today)
    if result.checksums_valid:
        return result
    cleaned = result.raw
    fields = _FIELDS[detect_format(cleaned)]
    positions = [
        (line, col)
        for line, start, end in fields
        for col in range(start, end)
        if cleaned[line][col] in _SWAPS
    ]
    for count in range(1, _MAX_SWAPS + 1):
        valid: list[tuple[MrzResult, tuple[tuple[int, int], ...]]] = []
        for variant, swapped in _candidates(cleaned, positions, count):
            candidate = parse_mrz(variant, today=today)
            if candidate.checksums_valid:
                valid.append((candidate, swapped))
        if len(valid) == 1:
            fixed, swapped = valid[0]
            corrections = tuple(sorted({*fixed.corrections, *swapped}))
            return fixed.model_copy(update={"raw": cleaned, "corrections": corrections})
        if valid:
            break  # plusieurs variantes valides : ambiguïté, on ne choisit pas
    return result


def has_undetectable_confusion(result: MrzResult) -> bool:
    """Vrai si une ou deux confusions `O`/`0` dans le numéro laisseraient toutes les clés valides.

    Le modèle de reconnaissance confond `O` et `0` ; deux confusions peuvent s'annuler dans
    la clé (24 x 3 + 24 x 7 = 240). Un tel numéro ne peut pas être garanti par la MRZ seule.
    """
    if not result.checksums_valid:
        return False
    line, start, end = _FIELDS[result.format][1 if result.format is MrzFormat.FR_LEGACY else 0]
    # Analyse du numéro retenu, pas de la lecture brute : une confusion déjà corrigée de
    # façon univoque par `parse_mrz_tolerant` ne rend pas le numéro ambigu.
    number = result.document_number.ljust(end - start, "<")[: end - start]
    lines = list(result.raw)
    lines[line] = lines[line][:start] + number + lines[line][end:]
    positions = [(line, col) for col in range(start, end) if lines[line][col] in "O0"]
    flip = {"O": "0", "0": "O"}
    for count in (1, 2):
        for chosen in combinations(positions, count):
            variant = [list(row) for row in lines]
            for row, col in chosen:
                variant[row][col] = flip[variant[row][col]]
            try:
                if parse_mrz(["".join(row) for row in variant]).checksums_valid:
                    return True
            except MrzError:
                continue
    return False
