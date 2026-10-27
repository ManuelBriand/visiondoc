"""Somme de contrôle ICAO 9303 (pondération 7-3-1, modulo 10)."""

_WEIGHTS = (7, 3, 1)


def char_value(char: str) -> int:
    """Valeur d'un caractère MRZ : 0-9, A-Z → 10-35, `<` → 0."""
    if len(char) != 1:
        raise ValueError("un seul caractère attendu")
    if "0" <= char <= "9":
        return ord(char) - ord("0")
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    if char == "<":
        return 0
    raise ValueError("caractère hors de l'alphabet MRZ")


def check_digit(data: str) -> int:
    return sum(char_value(c) * _WEIGHTS[i % 3] for i, c in enumerate(data)) % 10


def verify(data: str, digit: str) -> bool:
    """Vrai si `digit` est la clé de `data`.

    Une clé `<` n'est admise que pour un champ entièrement vide (numéro personnel TD3).
    """
    if digit == "<":
        return all(c == "<" for c in data)
    if not digit.isdigit():
        return False
    return check_digit(data) == int(digit)
