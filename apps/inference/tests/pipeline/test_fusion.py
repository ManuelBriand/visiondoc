from datetime import date

import pytest

from inference.mrz import MrzResult, parse_mrz
from inference.mrz.generator import MrzIdentity, build_fr_legacy, build_td1, build_td3
from inference.pipeline.fusion import document_type, fuse
from inference.pipeline.visual_fields import FieldValue, VisualValue

TODAY = date(2026, 10, 22)


def _identity(**changes: object) -> MrzIdentity:
    base: dict[str, object] = {
        "last_name": "Martin",
        "first_names": ("Camille", "Marie"),
        "document_number": "X4RTBPFW4",
        "birth_date": date(1990, 4, 12),
        "sex": "F",
        "expiry_date": date(2031, 6, 30),
    }
    base.update(changes)
    return MrzIdentity(**base)  # type: ignore[arg-type]


def _td1(**changes: object) -> MrzResult:
    return parse_mrz(build_td1(_identity(**changes)), today=TODAY)


def _seen(**fields: FieldValue) -> dict[str, VisualValue]:
    return {name: VisualValue(value, 0.99) for name, value in fields.items()}


def test_valid_mrz_fields_have_full_confidence() -> None:
    fields, checks, warnings = fuse(
        _td1(),
        _seen(last_name="MARTIN", birth_date=date(1990, 4, 12), birth_place="LYON"),
        TODAY,
    )
    assert fields["last_name"].confidence == 1.0
    assert fields["last_name"].source == "mrz"
    assert fields["birth_date"].value == "1990-04-12"
    assert fields["first_names"].value == ["CAMILLE", "MARIE"]
    assert fields["birth_place"].model_dump() == {
        "value": "LYON",
        "confidence": 0.7,
        "source": "ocr",
    }
    assert {c.code: c.status for c in checks} == {
        "mrz_checksums": "pass",
        "mrz_matches_visual": "pass",
        "document_expired": "pass",
    }
    assert warnings == []
    assert list(fields) == [
        "last_name",
        "first_names",
        "birth_date",
        "sex",
        "document_number",
        "expiry_date",
        "birth_place",
    ]


def test_mismatch_keeps_mrz_value_and_warns() -> None:
    fields, checks, warnings = fuse(_td1(), _seen(birth_date=date(1990, 4, 13)), TODAY)
    assert fields["birth_date"].value == "1990-04-12"
    assert {c.code: c.status for c in checks}["mrz_matches_visual"] == "fail"
    assert [(w.code, w.field) for w in warnings] == [("mrz_visual_mismatch", "birth_date")]


def test_truncated_first_names_are_completed_by_visual_zone() -> None:
    mrz = _td1(first_names=("Maximilienne", "Gwendoline"))
    assert mrz.first_names == ("MAXIMILIENNE", "GWENDOLIN")
    fields, _, warnings = fuse(mrz, _seen(first_names=("MAXIMILIENNE", "GWENDOLINE")), TODAY)
    assert fields["first_names"].model_dump() == {
        "value": ["MAXIMILIENNE", "GWENDOLINE"],
        "confidence": 0.9,
        "source": "ocr",
    }
    assert warnings == []


def test_invalid_mrz_falls_back_to_field_checks_and_visual_agreement() -> None:
    l1, l2, l3 = build_td1(_identity())
    broken = parse_mrz([l1, l2[:29] + str((int(l2[29]) + 1) % 10), l3], today=TODAY)
    assert not broken.checksums_valid
    fields, checks, warnings = fuse(broken, _seen(last_name="MARTIN"), TODAY)
    assert fields["birth_date"].confidence == 1.0  # clé du champ valide
    assert fields["last_name"].confidence == 0.9  # confirmé par la zone visuelle
    assert fields["sex"].confidence == 0.7  # ni clé ni confirmation
    assert {c.code: c.status for c in checks}["mrz_checksums"] == "fail"
    assert "mrz_checksums_invalid" in [w.code for w in warnings]


def test_expired_document() -> None:
    _, checks, _ = fuse(_td1(expiry_date=date(2026, 10, 21)), {}, TODAY)
    assert {c.code: c.status for c in checks}["document_expired"] == "fail"
    assert {c.code: c.status for c in checks}["mrz_matches_visual"] == "undetermined"


def test_issue_date_confirmed_by_ten_year_validity() -> None:
    fields, _, _ = fuse(_td1(), _seen(issue_date=date(2021, 6, 30)), TODAY)
    assert fields["issue_date"].confidence == 0.9
    fields, _, _ = fuse(_td1(), _seen(issue_date=date(2022, 1, 5)), TODAY)
    assert fields["issue_date"].confidence == 0.7


def _legacy(birth: date) -> MrzResult:
    identity = _identity(
        document_number="100692310285",
        birth_date=birth,
        expiry_date=None,
        optional_data="923102",
    )
    return parse_mrz(build_fr_legacy(identity), today=TODAY)


def test_legacy_card_issued_2004_2013_to_adult_gains_five_years() -> None:
    fields, checks, warnings = fuse(
        _legacy(date(1980, 1, 1)),
        _seen(issue_date=date(2010, 6, 1), expiry_date=date(2020, 6, 1)),
        TODAY,
    )
    assert fields["expiry_date"].model_dump() == {
        "value": "2025-06-01",
        "confidence": 0.9,
        "source": "computed",
    }
    assert fields["issue_date"].confidence == 0.9
    assert {c.code: c.status for c in checks}["document_expired"] == "fail"
    assert ("validity_extended", "expiry_date") in [(w.code, w.field) for w in warnings]


def test_legacy_extension_uses_printed_date_when_issue_date_is_missing() -> None:
    fields, _, _ = fuse(_legacy(date(1980, 1, 1)), _seen(expiry_date=date(2022, 3, 1)), TODAY)
    assert fields["expiry_date"].value == "2027-03-01"
    assert fields["expiry_date"].confidence == 0.7


@pytest.mark.parametrize(
    ("birth", "issue", "expected"),
    [
        (date(1997, 1, 1), date(2010, 6, 1), "2020-06-01"),  # mineur à la délivrance
        (date(1980, 1, 1), date(2014, 6, 1), "2024-06-01"),  # après 2013
        (date(1980, 1, 1), date(2003, 6, 1), "2013-06-01"),  # avant 2004
    ],
)
def test_legacy_extension_does_not_apply(birth: date, issue: date, expected: str) -> None:
    printed = issue.replace(year=issue.year + 10)
    fields, _, warnings = fuse(_legacy(birth), _seen(issue_date=issue, expiry_date=printed), TODAY)
    assert fields["expiry_date"].value == expected
    assert fields["expiry_date"].source == "ocr"
    assert "validity_extended" not in [w.code for w in warnings]


def test_legacy_without_back_side_has_unknown_expiry() -> None:
    fields, checks, warnings = fuse(_legacy(date(1980, 1, 1)), {}, TODAY)
    assert "expiry_date" not in fields
    assert {c.code: c.status for c in checks}["document_expired"] == "undetermined"
    assert ("expiry_unknown", "expiry_date") in [(w.code, w.field) for w in warnings]


def test_ambiguous_document_number_is_capped() -> None:
    # Positions 1 et 6 du numéro, de poids 3 et 7 : deux confusions O/0 s'annuleraient.
    fields, _, warnings = fuse(_td1(document_number="W09TCH0XC"), {}, TODAY)
    assert fields["document_number"].confidence == 0.9
    assert ("document_number_ambiguous", "document_number") in [(w.code, w.field) for w in warnings]
    fields, _, _ = fuse(_td1(document_number="W19TCH2XC"), {}, TODAY)
    assert fields["document_number"].confidence == 1.0


def test_passport_has_nationality() -> None:
    mrz = parse_mrz(build_td3(_identity(document_number="12AB34567")), today=TODAY)
    fields, _, _ = fuse(mrz, {}, TODAY)
    assert fields["nationality"].value == "FRA"


def test_document_type() -> None:
    assert document_type(_td1()) == "fr_id_card_2021"
    assert document_type(_legacy(date(1980, 1, 1))) == "fr_id_card_legacy"
    passport = parse_mrz(build_td3(_identity()), today=TODAY)
    assert document_type(passport) == "fr_passport"
    foreign = parse_mrz(build_td3(_identity(issuing_country="UTO")), today=TODAY)
    assert document_type(foreign) is None


def test_prefix_is_not_agreement_when_mrz_name_is_complete() -> None:
    # MRZ « MARTIN » complète, zone visuelle mal lue « MARTINI » : désaccord, valeur MRZ.
    fields, checks, warnings = fuse(_td1(), _seen(last_name="MARTINI"), TODAY)
    assert fields["last_name"].value == "MARTIN"
    assert fields["last_name"].source == "mrz"
    assert {c.code: c.status for c in checks}["mrz_matches_visual"] == "fail"
    assert ("mrz_visual_mismatch", "last_name") in [(w.code, w.field) for w in warnings]


def test_compound_first_name_takes_visual_segmentation() -> None:
    mrz = _td1(first_names=("Jean-Pierre", "Marc"))
    assert mrz.first_names == ("JEAN", "PIERRE", "MARC")
    fields, checks, warnings = fuse(mrz, _seen(first_names=("JEAN PIERRE", "MARC")), TODAY)
    assert fields["first_names"].model_dump() == {
        "value": ["JEAN PIERRE", "MARC"],
        "confidence": 0.9,
        "source": "ocr",
    }
    assert {c.code: c.status for c in checks}["mrz_matches_visual"] == "pass"
    assert warnings == []


def test_field_with_wrong_check_digit_is_not_rescued_by_visual_zone() -> None:
    l1, l2, l3 = build_td1(_identity())
    misread = l1.replace("X4RTBPFW4", "X4RTBPFWA")  # clé du numéro désormais fausse
    mrz = parse_mrz([misread, l2, l3], today=TODAY)
    assert mrz.checks["document_number"] is False
    fields, _, warnings = fuse(mrz, _seen(document_number="X4RTBPFWA"), TODAY)
    assert fields["document_number"].confidence == 0.3
    assert ("check_digit_invalid", "document_number") in [(w.code, w.field) for w in warnings]


def test_legacy_first_names_cut_inside_a_separator_are_completed() -> None:
    identity = _identity(
        first_names=("Chloé", "Maëlle", "Léa"),
        document_number="100692310285",
        expiry_date=None,
        optional_data="923102",
    )
    mrz = parse_mrz(build_fr_legacy(identity), today=TODAY)
    assert mrz.raw[1][13:27] == "CHLOE<<MAELLE<"
    fields, _, warnings = fuse(mrz, _seen(first_names=("CHLOE", "MAELLE", "LEA")), TODAY)
    assert fields["first_names"].value == ["CHLOE", "MAELLE", "LEA"]
    assert fields["first_names"].source == "ocr"
    assert "mrz_visual_mismatch" not in [w.code for w in warnings]
