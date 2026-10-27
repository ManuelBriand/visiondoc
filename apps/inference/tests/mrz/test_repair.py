from datetime import date

import pytest

from inference.mrz import MrzError, parse_mrz
from inference.mrz.generator import MrzIdentity, build_fr_legacy, build_td1, build_td3
from inference.mrz.repair import has_undetectable_confusion, parse_mrz_tolerant

TODAY = date(2026, 10, 22)


def _identity(number: str) -> MrzIdentity:
    return MrzIdentity(
        last_name="Martin",
        first_names=("Camille",),
        document_number=number,
        birth_date=date(1990, 4, 12),
        sex="F",
        expiry_date=date(2031, 6, 30),
    )


def test_valid_mrz_is_untouched() -> None:
    lines = build_td3(_identity("12AB34567"))
    assert parse_mrz_tolerant(lines, today=TODAY) == parse_mrz(lines, today=TODAY)


def test_single_unique_confusion_is_fixed() -> None:
    l1, l2 = build_td3(_identity("12AB34507"))
    misread = l2.replace("34507", "345O7", 1)
    result = parse_mrz_tolerant([l1, misread], today=TODAY)
    assert result.checksums_valid
    assert result.document_number == "12AB34507"
    assert (1, 7) in result.corrections
    assert result.raw[1] == misread


def test_ambiguous_confusion_is_left_invalid() -> None:
    # Deux `O` aux positions 4 et 7 du numéro : même poids (3) dans chaque clé,
    # donc corriger l'un ou l'autre rend la MRZ valide. On ne choisit pas.
    l1, l2, l3 = build_td1(_identity("EH6GOKP05"))
    misread = l1.replace("EH6GOKP05", "EH6GOKPO5")
    result = parse_mrz_tolerant([misread, l2, l3], today=TODAY)
    assert not result.checksums_valid
    assert result.document_number == "EH6GOKPO5"


def test_unrelated_error_is_not_masked() -> None:
    l1, l2 = build_td3(_identity("12AB34567"))
    wrong_birth = l2[:13] + "900413" + l2[19:]
    result = parse_mrz_tolerant([l1, wrong_birth], today=TODAY)
    assert not result.checksums_valid


def test_legacy_prefix_with_one_misread_char_is_restored() -> None:
    identity = MrzIdentity(
        last_name="Martin",
        first_names=("Camille",),
        document_number="880692310285",
        birth_date=date(1990, 4, 12),
        sex="F",
        optional_data="921031",
    )
    l1, l2 = build_fr_legacy(identity)
    result = parse_mrz_tolerant(["Q" + l1[1:], l2], today=TODAY)
    assert result.checksums_valid
    assert result.last_name == "MARTIN"
    assert (0, 0) in result.corrections
    assert result.raw[0].startswith("QDFRA")


def test_legacy_prefix_with_two_misread_chars_is_not_guessed() -> None:
    identity = MrzIdentity(
        last_name="Martin",
        first_names=("Camille",),
        document_number="880692310285",
        birth_date=date(1990, 4, 12),
        sex="F",
        optional_data="921031",
    )
    l1, l2 = build_fr_legacy(identity)
    with pytest.raises(MrzError):
        parse_mrz_tolerant(["QOFRA" + l1[5:], l2], today=TODAY)


def test_cancelling_double_confusion_is_detected() -> None:
    result = parse_mrz(build_td1(_identity("W09TCH0XC")), today=TODAY)
    assert has_undetectable_confusion(result)


def test_single_confusion_repaired_unambiguously_is_not_flagged() -> None:
    l1, l2, l3 = build_td1(_identity("4EA4Q9OM4"))
    misread = l1.replace("Q9OM4", "Q90M4")  # O lu 0, corrigé sans ambiguïté
    result = parse_mrz_tolerant([misread, l2, l3], today=TODAY)
    assert result.checksums_valid
    assert result.document_number == "4EA4Q9OM4"
    assert not has_undetectable_confusion(result)


def test_invalid_mrz_is_never_called_ambiguous() -> None:
    l1, l2, l3 = build_td1(_identity("W09TCH0XC"))
    broken = parse_mrz([l1, l2[:29] + "0", l3], today=TODAY)
    assert not broken.checksums_valid
    assert not has_undetectable_confusion(broken)
