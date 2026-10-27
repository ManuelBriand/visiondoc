"""Construction de MRZ synthétiques valides, pour les tests et les spécimens générés."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from inference.mrz.checksum import check_digit
from inference.mrz.models import Sex


@dataclass(frozen=True)
class MrzIdentity:
    last_name: str
    first_names: tuple[str, ...]
    document_number: str
    birth_date: date
    sex: Sex | None
    expiry_date: date | None = None
    nationality: str = "FRA"
    issuing_country: str = "FRA"
    optional_data: str = field(default="")


def encode_text(text: str) -> str:
    """Majuscules sans accents ; espaces, tirets et apostrophes deviennent `<`."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z<]", "", re.sub(r"[ \-']", "<", ascii_text.upper()))


def _fit(value: str, width: int) -> str:
    return value[:width].ljust(width, "<")


def _cd(value: str) -> str:
    return str(check_digit(value))


def _yymmdd(value: date) -> str:
    return value.strftime("%y%m%d")


def _sex(value: Sex | None) -> str:
    return value or "<"


def _icao_name(identity: MrzIdentity, width: int) -> str:
    given = "<".join(encode_text(name) for name in identity.first_names)
    return _fit(f"{encode_text(identity.last_name)}<<{given}", width)


def build_td3(identity: MrzIdentity) -> tuple[str, str]:
    if identity.expiry_date is None:
        raise ValueError("un passeport a une date d'expiration")
    l1 = _fit("P<" + identity.issuing_country + _icao_name(identity, 39), 44)
    number = _fit(identity.document_number, 9)
    birth = _yymmdd(identity.birth_date)
    expiry = _yymmdd(identity.expiry_date)
    personal = _fit(identity.optional_data, 14)
    body = (
        number
        + _cd(number)
        + identity.nationality
        + birth
        + _cd(birth)
        + _sex(identity.sex)
        + expiry
        + _cd(expiry)
        + personal
        + _cd(personal)
    )
    composite = body[0:10] + body[13:20] + body[21:43]
    return l1, body + _cd(composite)


def build_td1(identity: MrzIdentity) -> tuple[str, str, str]:
    if identity.expiry_date is None:
        raise ValueError("une CNI au format TD1 a une date d'expiration")
    number = _fit(identity.document_number, 9)
    l1 = _fit("ID" + identity.issuing_country + number + _cd(number) + identity.optional_data, 30)
    birth = _yymmdd(identity.birth_date)
    expiry = _yymmdd(identity.expiry_date)
    l2_body = (
        birth
        + _cd(birth)
        + _sex(identity.sex)
        + expiry
        + _cd(expiry)
        + identity.nationality
        + "<" * 11
    )
    composite = l1[5:30] + l2_body[0:7] + l2_body[8:15] + l2_body[18:29]
    return l1, l2_body + _cd(composite), _icao_name(identity, 30)


def build_fr_legacy(identity: MrzIdentity) -> tuple[str, str]:
    """`optional_data` porte le département et le bureau d'émission (6 caractères)."""
    l1 = "IDFRA" + _fit(encode_text(identity.last_name), 25) + _fit(identity.optional_data, 6)
    number = _fit(identity.document_number, 12)
    given = _fit("<<".join(encode_text(name) for name in identity.first_names), 14)
    birth = _yymmdd(identity.birth_date)
    l2_body = number + _cd(number) + given + birth + _cd(birth) + _sex(identity.sex)
    return l1, l2_body + _cd(l1 + l2_body)
