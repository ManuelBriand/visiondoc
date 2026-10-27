"""Nouvelle CNI (2021) : 3 lignes de 30 caractères, au verso."""

from datetime import date

from inference.mrz.checksum import verify
from inference.mrz.dates import parse_birth_date, parse_expiry_date
from inference.mrz.errors import MrzError
from inference.mrz.fields import parse_country, parse_icao_name, parse_sex, strip_filler
from inference.mrz.models import MrzFormat, MrzResult
from inference.mrz.normalize import Span

DIGIT_SPANS: tuple[Span, ...] = ((0, 14, 15), (1, 0, 7), (1, 8, 15), (1, 29, 30))
LETTER_SPANS: tuple[Span, ...] = ((0, 2, 5), (1, 15, 18), (2, 0, 30))


def parse(lines: tuple[str, ...], today: date) -> MrzResult:
    l1, l2, l3 = lines
    if l1[0] not in ("I", "A", "C"):
        raise MrzError("unsupported_format", "MRZ de 3 lignes qui n'est pas une carte d'identité")
    birth_date = parse_birth_date(l2[0:6], today)
    expiry_date = parse_expiry_date(l2[8:14], today)
    last_name, first_names = parse_icao_name(l3)
    optional = (l1[15:30] + l2[18:29]).replace("<", "")
    return MrzResult(
        format=MrzFormat.TD1,
        document_code=strip_filler(l1[0:2]),
        issuing_country=parse_country(l1[2:5]),
        last_name=last_name,
        first_names=first_names,
        document_number=l1[5:14].replace("<", ""),
        nationality=parse_country(l2[15:18]),
        birth_date=birth_date,
        sex=parse_sex(l2[7]),
        expiry_date=expiry_date,
        optional_data=optional,
        checks={
            "document_number": verify(l1[5:14], l1[14]),
            "birth_date": birth_date is not None and verify(l2[0:6], l2[6]),
            "expiry_date": expiry_date is not None and verify(l2[8:14], l2[14]),
            "composite": verify(l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29], l2[29]),
        },
        raw=lines,
    )
