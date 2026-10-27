"""Dates MRZ (YYMMDD) vers `date`, avec pivot de siècle selon la nature du champ."""

from datetime import date

# Une date d'expiration au-delà de cette marge est considérée comme du siècle précédent.
_EXPIRY_HORIZON_YEARS = 50


def _build(value: str, century: int) -> date | None:
    if len(value) != 6 or not value.isdigit():
        return None
    try:
        return date(century + int(value[0:2]), int(value[2:4]), int(value[4:6]))
    except ValueError:
        return None


def parse_birth_date(value: str, today: date) -> date | None:
    """Une date de naissance n'est jamais dans le futur."""
    candidate = _build(value, 2000)
    if candidate is None or candidate <= today:
        return candidate
    return _build(value, 1900)


def parse_expiry_date(value: str, today: date) -> date | None:
    candidate = _build(value, 2000)
    if candidate is None or candidate.year <= today.year + _EXPIRY_HORIZON_YEARS:
        return candidate
    return _build(value, 1900)
