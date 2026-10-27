"""Spécimens fictifs publiés dans ICAO Doc 9303 (État « Utopia »)."""

from datetime import date

from inference.mrz import MrzFormat, parse_mrz

TODAY = date(2026, 10, 22)


def test_td3_specimen() -> None:
    result = parse_mrz(
        [
            "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
            "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
        ],
        today=TODAY,
    )
    assert result.format is MrzFormat.TD3
    assert result.document_code == "P"
    assert result.issuing_country == "UTO"
    assert result.last_name == "ERIKSSON"
    assert result.first_names == ("ANNA", "MARIA")
    assert result.document_number == "L898902C3"
    assert result.nationality == "UTO"
    assert result.birth_date == date(1974, 8, 12)
    assert result.sex == "F"
    assert result.expiry_date == date(2012, 4, 15)
    assert result.optional_data == "ZE184226B"
    assert result.checksums_valid
    assert result.corrections == ()


def test_td1_specimen() -> None:
    result = parse_mrz(
        [
            "I<UTOD231458907<<<<<<<<<<<<<<<",
            "7408122F1204159UTO<<<<<<<<<<<6",
            "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
        ],
        today=TODAY,
    )
    assert result.format is MrzFormat.TD1
    assert result.document_code == "I"
    assert result.document_number == "D23145890"
    assert result.last_name == "ERIKSSON"
    assert result.first_names == ("ANNA", "MARIA")
    assert result.birth_date == date(1974, 8, 12)
    assert result.expiry_date == date(2012, 4, 15)
    assert result.checksums_valid
