"""Ancienne CNI française : 2 lignes de 36 caractères.

Ligne 1 : `IDFRA` + nom (25) + département et bureau d'émission (6).
Ligne 2 : numéro (12) + clé + prénoms (14) + naissance (6) + clé + sexe + clé globale.
La clé globale porte sur la ligne 1 entière et les 35 premiers caractères de la ligne 2.
Pas de date d'expiration ni de nationalité dans la MRZ.
"""

from datetime import date

from inference.mrz.checksum import verify
from inference.mrz.dates import parse_birth_date
from inference.mrz.fields import parse_legacy_given_names, parse_sex, parse_surname
from inference.mrz.models import MrzFormat, MrzResult
from inference.mrz.normalize import Span

PREFIX = "IDFRA"

DIGIT_SPANS: tuple[Span, ...] = ((1, 12, 13), (1, 27, 34), (1, 35, 36))
LETTER_SPANS: tuple[Span, ...] = ((0, 5, 30), (1, 13, 27))


def parse(lines: tuple[str, ...], today: date) -> MrzResult:
    l1, l2 = lines
    birth_date = parse_birth_date(l2[27:33], today)
    return MrzResult(
        format=MrzFormat.FR_LEGACY,
        document_code="ID",
        issuing_country="FRA",
        last_name=parse_surname(l1[5:30]),
        first_names=parse_legacy_given_names(l2[13:27]),
        document_number=l2[0:12].replace("<", ""),
        nationality=None,
        birth_date=birth_date,
        sex=parse_sex(l2[34]),
        expiry_date=None,
        optional_data=l1[30:36].replace("<", ""),
        checks={
            "document_number": verify(l2[0:12], l2[12]),
            "birth_date": birth_date is not None and verify(l2[27:33], l2[33]),
            "composite": verify(l1 + l2[0:35], l2[35]),
        },
        raw=lines,
    )
