"""Propriété : lire la MRZ générée à partir d'une identité redonne cette identité."""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from inference.mrz import Sex, parse_mrz
from inference.mrz.generator import MrzIdentity, build_fr_legacy, build_td1, build_td3

TODAY = date(2026, 10, 22)

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALNUM = UPPER + "0123456789"

word = st.text(UPPER, min_size=1, max_size=5)
surname = st.lists(st.text(UPPER, min_size=1, max_size=8), min_size=1, max_size=2).map(" ".join)
sex: st.SearchStrategy[Sex | None] = st.sampled_from(["M", "F", None])
birth = st.dates(min_value=date(1927, 1, 1), max_value=TODAY)
expiry = st.dates(min_value=date(2000, 1, 1), max_value=date(2076, 12, 31))


@st.composite
def icao_identity(draw: st.DrawFn) -> MrzIdentity:
    return MrzIdentity(
        last_name=draw(surname),
        first_names=tuple(draw(st.lists(word, min_size=1, max_size=2))),
        document_number=draw(st.text(ALNUM, min_size=9, max_size=9)),
        birth_date=draw(birth),
        sex=draw(sex),
        expiry_date=draw(expiry),
    )


@st.composite
def legacy_identity(draw: st.DrawFn) -> MrzIdentity:
    return MrzIdentity(
        last_name=draw(surname),
        first_names=tuple(draw(st.lists(word, min_size=1, max_size=2))),
        document_number=draw(st.text("0123456789", min_size=12, max_size=12)),
        birth_date=draw(birth),
        sex=draw(sex),
        optional_data=draw(st.text(ALNUM, min_size=6, max_size=6)),
    )


def _assert_matches(identity: MrzIdentity, lines: tuple[str, ...]) -> None:
    result = parse_mrz(lines, today=TODAY)
    assert result.checksums_valid
    assert result.corrections == ()
    assert result.last_name == identity.last_name
    assert result.first_names == identity.first_names
    assert result.document_number == identity.document_number
    assert result.birth_date == identity.birth_date
    assert result.sex == identity.sex
    assert result.expiry_date == identity.expiry_date


@given(icao_identity())
def test_td1_roundtrip(identity: MrzIdentity) -> None:
    _assert_matches(identity, build_td1(identity))


@given(icao_identity())
def test_td3_roundtrip(identity: MrzIdentity) -> None:
    _assert_matches(identity, build_td3(identity))


@given(legacy_identity())
def test_fr_legacy_roundtrip(identity: MrzIdentity) -> None:
    lines = build_fr_legacy(identity)
    _assert_matches(identity, lines)
    assert parse_mrz(lines, today=TODAY).optional_data == identity.optional_data
