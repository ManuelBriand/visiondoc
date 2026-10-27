"""Les trois formats sur des identités synthétiques."""

from datetime import date

import pytest

from inference.mrz import MrzError, MrzFormat, parse_mrz
from inference.mrz.checksum import check_digit
from inference.mrz.dates import parse_birth_date, parse_expiry_date
from inference.mrz.generator import (
    MrzIdentity,
    build_fr_legacy,
    build_td1,
    build_td3,
    encode_text,
)

TODAY = date(2026, 10, 22)

CAMILLE = MrzIdentity(
    last_name="Martin",
    first_names=("Camille", "Marie"),
    document_number="X4RTBPFW4",
    birth_date=date(1990, 4, 12),
    sex="F",
    expiry_date=date(2031, 6, 30),
)


def test_td1_new_id_card() -> None:
    lines = build_td1(CAMILLE)
    assert [len(line) for line in lines] == [30, 30, 30]
    result = parse_mrz(lines, today=TODAY)
    assert result.format is MrzFormat.TD1
    assert result.document_code == "ID"
    assert result.issuing_country == "FRA"
    assert result.last_name == "MARTIN"
    assert result.first_names == ("CAMILLE", "MARIE")
    assert result.document_number == "X4RTBPFW4"
    assert result.nationality == "FRA"
    assert result.birth_date == date(1990, 4, 12)
    assert result.sex == "F"
    assert result.expiry_date == date(2031, 6, 30)
    assert result.checksums_valid
    assert set(result.checks) == {"document_number", "birth_date", "expiry_date", "composite"}


def test_td3_passport() -> None:
    identity = MrzIdentity(
        last_name="De La Fontaine",
        first_names=("Jean",),
        document_number="23AB45678",
        birth_date=date(2001, 1, 31),
        sex="M",
        expiry_date=date(2033, 2, 1),
    )
    lines = build_td3(identity)
    assert [len(line) for line in lines] == [44, 44]
    result = parse_mrz(lines, today=TODAY)
    assert result.format is MrzFormat.TD3
    assert result.last_name == "DE LA FONTAINE"
    assert result.first_names == ("JEAN",)
    assert result.document_number == "23AB45678"
    assert result.birth_date == date(2001, 1, 31)
    assert result.optional_data == ""
    assert result.checksums_valid


def test_fr_legacy_id_card() -> None:
    identity = MrzIdentity(
        last_name="Lefèvre",
        first_names=("Jean Pierre", "Marc"),
        document_number="880692310285",
        birth_date=date(1972, 11, 3),
        sex="M",
        optional_data="921031",
    )
    lines = build_fr_legacy(identity)
    assert lines[1][13:27] == "JEAN<PIERRE<<M"  # prénoms tronqués à 14 caractères
    result = parse_mrz(lines, today=TODAY)
    assert result.format is MrzFormat.FR_LEGACY
    assert result.last_name == "LEFEVRE"
    assert result.first_names == ("JEAN PIERRE", "M")
    assert result.document_number == "880692310285"
    assert result.birth_date == date(1972, 11, 3)
    assert result.expiry_date is None
    assert result.nationality is None
    assert result.optional_data == "921031"
    assert result.checksums_valid
    assert set(result.checks) == {"document_number", "birth_date", "composite"}


def test_names_fill_entire_field_without_filler() -> None:
    identity = MrzIdentity(
        last_name="Wolfeschlegelsteinhausen",
        first_names=("Bartholomew",),
        document_number="X4RTBPFW4",
        birth_date=date(1990, 4, 12),
        sex=None,
        expiry_date=date(2031, 6, 30),
    )
    result = parse_mrz(build_td1(identity), today=TODAY)
    assert result.last_name == "WOLFESCHLEGELSTEINHAUSEN"
    assert result.first_names == ("BART",)  # tronqué par la largeur du champ
    assert result.sex is None
    assert result.checksums_valid


def test_input_is_cleaned() -> None:
    lines = build_td1(CAMILLE)
    messy = ["  " + lines[0].lower() + "\n", "", lines[1], lines[2] + "  "]
    assert parse_mrz(messy, today=TODAY).checksums_valid


def test_ocr_confusions_corrected_in_numeric_fields_only() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    # Naissance 900412 lue « 9OO4I2 ».
    noisy_l2 = "9OO4I2" + l2[6:]
    result = parse_mrz([l1, noisy_l2, l3], today=TODAY)
    assert result.birth_date == date(1990, 4, 12)
    assert result.checksums_valid
    assert result.corrections == ((1, 1), (1, 2), (1, 4))
    assert result.raw[1] == noisy_l2


def test_ocr_confusions_corrected_in_name_and_country_fields() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    # « MARTIN<<CAMILLE » lu « MART1N<<CAM1LLE ».
    noisy_l3 = l3.replace("MARTIN", "MART1N").replace("CAMILLE", "CAM1LLE")
    result = parse_mrz([l1, l2, noisy_l3], today=TODAY)
    assert result.last_name == "MARTIN"
    assert result.first_names == ("CAMILLE", "MARIE")
    assert result.corrections == ((2, 4), (2, 11))


def test_legacy_name_misread_digit_fixed_before_composite() -> None:
    identity = MrzIdentity(
        last_name="Moreau",
        first_names=("Odile",),
        document_number="880692310285",
        birth_date=date(1972, 11, 3),
        sex="F",
        optional_data="921031",
    )
    l1, l2 = build_fr_legacy(identity)
    result = parse_mrz([l1.replace("MOREAU", "M0REAU"), l2.replace("ODILE", "0DILE")], today=TODAY)
    assert result.last_name == "MOREAU"
    assert result.first_names == ("ODILE",)
    assert result.checksums_valid


@pytest.mark.parametrize("bad", ["MART3N", "MART7N"])
def test_unmappable_digit_in_name_is_rejected(bad: str) -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    with pytest.raises(MrzError) as excinfo:
        parse_mrz([l1, l2, l3.replace("MARTIN", bad)], today=TODAY)
    assert excinfo.value.code == "invalid_field"


def test_wrong_check_digit_flags_only_that_field() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    wrong = str((int(l2[6]) + 1) % 10)
    result = parse_mrz([l1, l2[:6] + wrong + l2[7:], l3], today=TODAY)
    assert not result.checksums_valid
    assert result.checks["birth_date"] is False
    assert result.checks["document_number"] is True


def test_impossible_date_is_invalid() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    body = "901312"  # mois 13
    l2 = body + str(check_digit(body)) + l2[7:]
    result = parse_mrz([l1, l2, l3], today=TODAY)
    assert result.birth_date is None
    assert result.checks["birth_date"] is False


@pytest.mark.parametrize(
    ("lines", "code"),
    [
        (["IDFRA<<<"], "invalid_length"),
        (["A" * 30, "A" * 30], "invalid_length"),
        (["P<FRA" + "<" * 39, "<" * 43], "invalid_length"),
        (["X" * 44, "<" * 44], "unsupported_format"),
        (["I<UTO" + "<" * 31, "<" * 36], "unsupported_format"),
        (["P" * 30, "<" * 30, "<" * 30], "unsupported_format"),
        (["IDFRA«" + "<" * 24, "<" * 30, "<" * 30], "invalid_characters"),
    ],
)
def test_errors(lines: list[str], code: str) -> None:
    with pytest.raises(MrzError) as excinfo:
        parse_mrz(lines, today=TODAY)
    assert excinfo.value.code == code


def test_error_message_never_contains_mrz_content() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    with pytest.raises(MrzError) as excinfo:
        parse_mrz([l1, l2[:7] + "Q" + l2[8:], l3], today=TODAY)
    assert excinfo.value.code == "invalid_field"
    assert "MARTIN" not in str(excinfo.value)
    assert l2 not in str(excinfo.value)


def test_invalid_country_code() -> None:
    l1, l2, l3 = build_td1(CAMILLE)
    with pytest.raises(MrzError) as excinfo:
        parse_mrz([l1, l2[:15] + "FR4" + l2[18:], l3], today=TODAY)
    assert excinfo.value.code == "invalid_field"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("261022", date(2026, 10, 22)),
        ("261023", date(1926, 10, 23)),
        ("000101", date(2000, 1, 1)),
        ("991231", date(1999, 12, 31)),
    ],
)
def test_birth_date_century(value: str, expected: date) -> None:
    assert parse_birth_date(value, TODAY) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("310630", date(2031, 6, 30)),
        ("120415", date(2012, 4, 15)),
        ("761231", date(2076, 12, 31)),
        ("770101", date(1977, 1, 1)),
    ],
)
def test_expiry_date_century(value: str, expected: date) -> None:
    assert parse_expiry_date(value, TODAY) == expected


@pytest.mark.parametrize("value", ["90041", "9004<2", "900230", "ABCDEF"])
def test_invalid_dates(value: str) -> None:
    assert parse_birth_date(value, TODAY) is None
    assert parse_expiry_date(value, TODAY) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Élodie", "ELODIE"),
        ("Jean-Pierre", "JEAN<PIERRE"),
        ("D'Arc", "D<ARC"),
        ("De la Fontaine", "DE<LA<FONTAINE"),
        ("Müller-Ødegård", "MULLER<DEGARD"),
    ],
)
def test_encode_text(text: str, expected: str) -> None:
    assert encode_text(text) == expected


def test_generator_requires_expiry_for_icao_formats() -> None:
    no_expiry = MrzIdentity(
        last_name="Martin",
        first_names=("Camille",),
        document_number="X4RTBPFW4",
        birth_date=date(1990, 4, 12),
        sex="F",
    )
    with pytest.raises(ValueError):
        build_td1(no_expiry)
    with pytest.raises(ValueError):
        build_td3(no_expiry)
