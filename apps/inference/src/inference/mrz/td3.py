"""Passeport : 2 lignes de 44 caractères."""

from datetime import date

from inference.mrz.checksum import verify
from inference.mrz.dates import parse_birth_date, parse_expiry_date
from inference.mrz.errors import MrzError
from inference.mrz.fields import parse_country, parse_icao_name, parse_sex, strip_filler
from inference.mrz.models import MrzFormat, MrzResult
from inference.mrz.normalize import Span

DIGIT_SPANS: tuple[Span, ...] = ((1, 9, 10), (1, 13, 20), (1, 21, 28), (1, 42, 44))
LETTER_SPANS: tuple[Span, ...] = ((0, 2, 44), (1, 10, 13))


def parse(lines: tuple[str, ...], today: date) -> MrzResult:
    l1, l2 = lines
    if l1[0] != "P":
        raise MrzError("unsupported_format", "MRZ de 44 caractères qui n'est pas un passeport")
    birth_date = parse_birth_date(l2[13:19], today)
    expiry_date = parse_expiry_date(l2[21:27], today)
    last_name, first_names = parse_icao_name(l1[5:44])
    return MrzResult(
        format=MrzFormat.TD3,
        document_code=strip_filler(l1[0:2]),
        issuing_country=parse_country(l1[2:5]),
        last_name=last_name,
        first_names=first_names,
        document_number=l2[0:9].replace("<", ""),
        nationality=parse_country(l2[10:13]),
        birth_date=birth_date,
        sex=parse_sex(l2[20]),
        expiry_date=expiry_date,
        optional_data=l2[28:42].replace("<", ""),
        checks={
            "document_number": verify(l2[0:9], l2[9]),
            "birth_date": birth_date is not None and verify(l2[13:19], l2[19]),
            "expiry_date": expiry_date is not None and verify(l2[21:27], l2[27]),
            "optional_data": verify(l2[28:42], l2[42]),
            "composite": verify(l2[0:10] + l2[13:20] + l2[21:43], l2[43]),
        },
        raw=lines,
    )
