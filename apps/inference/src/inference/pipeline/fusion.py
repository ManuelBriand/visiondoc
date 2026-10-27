"""Fusion de la MRZ et de la zone visuelle : valeurs, confiance, contrôles (spec A4).

Confiance :
- 1,0 : champ issu d'une MRZ valide (ou confirmé par sa propre clé) ;
- 0,9 : champ de la zone visuelle confirmé par la MRZ ou cohérent avec une autre source ;
- 0,7 : champ de la zone visuelle seul ;
- 0,3 : champ de la MRZ dont la propre clé de contrôle est fausse (spec B8, format invalide).
Exception (ADR 0004) : un numéro de document dont une double confusion `O`/`0` resterait
invisible pour les clés est plafonné à 0,9.

Fonctions pures : aucune I/O, la date de référence est un paramètre.
"""

from datetime import date

from inference.mrz import MrzFormat, MrzResult
from inference.mrz.repair import has_undetectable_confusion
from inference.pipeline.models import Check, CheckStatus, DocumentType, Field, Source, WarningItem
from inference.pipeline.visual_fields import FieldValue, VisualValue
from inference.text import compact

MRZ = 1.0
CONFIRMED = 0.9
OCR_ONLY = 0.7
INVALID = 0.3

# Décret n° 2013-1188 : CNI délivrées à des majeurs entre ces dates, validité portée à 15 ans.
_EXTENSION_START = date(2004, 1, 2)
_EXTENSION_END = date(2013, 12, 31)

_FIELD_ORDER = (
    "last_name",
    "first_names",
    "birth_date",
    "sex",
    "nationality",
    "document_number",
    "issue_date",
    "expiry_date",
    "birth_place",
)

_MESSAGES = {
    "mrz_checksums_invalid": "Une clé de contrôle de la MRZ est invalide : relecture conseillée.",
    "mrz_visual_mismatch": "La zone visuelle ne correspond pas à la MRZ pour ce champ.",
    "check_digit_invalid": "La clé de contrôle de ce champ est fausse : valeur à vérifier.",
    "document_number_ambiguous": (
        "Le numéro contient des O ou des 0 qu'aucune clé ne départage : vérifiez-le."
    ),
    "expiry_unknown": "Date d'expiration illisible ou absente : envoyez le verso de la carte.",
    "validity_extended": (
        "Carte délivrée entre 2004 et 2013 à un majeur : validité prolongée de 5 ans."
    ),
}


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _warning(code: str, field: str | None = None) -> WarningItem:
    return WarningItem(code=code, field=field, message=_MESSAGES[code])


def _serialize(value: FieldValue | list[str]) -> str | list[str]:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return list(value)
    return value


def truncated_names(mrz: MrzResult) -> set[str]:
    """Champs de nom peut-être tronqués par la MRZ : leur zone ne finit pas par `<<`.

    Un seul `<` final ne suffit pas : la coupure peut tomber au milieu d'un séparateur
    (`CHLOE<<MAELLE<` pour « Chloé, Maëlle, Léa »).
    """
    raw = mrz.raw
    if mrz.format is MrzFormat.FR_LEGACY:
        tails = {"last_name": raw[0][28:30], "first_names": raw[1][25:27]}
        return {name for name, tail in tails.items() if tail != "<<"}
    tail = raw[2][-2:] if mrz.format is MrzFormat.TD1 else raw[0][-2:]
    return set() if tail == "<<" else {"last_name", "first_names"}


def _agrees(field: str, mrz_value: FieldValue, visual: FieldValue, truncated: bool) -> bool:
    """Noms comparés sans espaces ni ponctuation ; un préfixe ne vaut accord que si la MRZ
    est réellement tronquée."""
    if field in ("last_name", "first_names"):

        def text(value: FieldValue) -> str:
            return compact(" ".join(value) if isinstance(value, tuple) else str(value))

        mrz_text, visual_text = text(mrz_value), text(visual)
        if not mrz_text:
            return False
        return visual_text == mrz_text or (truncated and visual_text.startswith(mrz_text))
    return mrz_value == visual


def _completes(mrz_value: FieldValue, visual: FieldValue) -> bool:
    """La zone visuelle donne une forme plus complète d'un nom : non tronquée, ou découpée
    correctement (la MRZ ne distingue pas « JEAN-PIERRE » de « JEAN », « PIERRE »)."""
    if not isinstance(visual, str | tuple) or isinstance(mrz_value, date):
        return False
    return visual != mrz_value


def document_type(mrz: MrzResult) -> DocumentType | None:
    if mrz.issuing_country != "FRA":
        return None
    if mrz.format is MrzFormat.FR_LEGACY:
        return "fr_id_card_legacy"
    if mrz.format is MrzFormat.TD1 and mrz.document_code == "ID":
        return "fr_id_card_2021"
    if mrz.format is MrzFormat.TD3 and mrz.document_code == "P":
        return "fr_passport"
    return None


def _date(visual: dict[str, VisualValue], name: str) -> date | None:
    seen = visual.get(name)
    return seen.value if seen is not None and isinstance(seen.value, date) else None


def _validity_years_match(issue: date, expiry: date) -> bool:
    """Délivrance et expiration cohérentes : validité de 5, 10 ou 15 ans, à un jour près."""
    return any(abs((expiry - _add_years(issue, years)).days) <= 1 for years in (5, 10, 15))


def fuse(
    mrz: MrzResult, visual: dict[str, VisualValue], today: date
) -> tuple[dict[str, Field], list[Check], list[WarningItem]]:
    fields: dict[str, Field] = {}
    warnings: list[WarningItem] = []
    if not mrz.checksums_valid:
        warnings.append(_warning("mrz_checksums_invalid"))

    mrz_values: dict[str, FieldValue] = {
        "last_name": mrz.last_name,
        "first_names": mrz.first_names,
        "sex": mrz.sex or "X",
        "document_number": mrz.document_number,
    }
    if mrz.birth_date is not None:
        mrz_values["birth_date"] = mrz.birth_date
    if mrz.expiry_date is not None:
        mrz_values["expiry_date"] = mrz.expiry_date
    if mrz.format is MrzFormat.TD3 and mrz.nationality:
        mrz_values["nationality"] = mrz.nationality

    compared: list[bool] = []
    truncated = truncated_names(mrz)
    for name, mrz_value in mrz_values.items():
        seen = visual.get(name)
        agrees = None if seen is None else _agrees(name, mrz_value, seen.value, name in truncated)
        if agrees is not None:
            compared.append(agrees)
            if not agrees:
                warnings.append(_warning("mrz_visual_mismatch", name))
        own_check = mrz.checks.get(name)
        value: FieldValue = mrz_value
        source: Source = "mrz"
        if own_check is False:
            # Clé fausse : signal négatif déterministe. Une zone visuelle concordante ne
            # rassure pas, l'OCR y fait les mêmes confusions O/0.
            confidence = INVALID
            warnings.append(_warning("check_digit_invalid", name))
        elif mrz.checksums_valid or own_check:
            confidence = MRZ
        else:
            confidence = CONFIRMED if agrees else OCR_ONLY
        if (
            seen is not None
            and agrees
            and name in ("last_name", "first_names")
            and _completes(mrz_value, seen.value)
        ):
            value, source, confidence = seen.value, "ocr", CONFIRMED
        if name == "document_number" and has_undetectable_confusion(mrz):
            confidence = min(confidence, CONFIRMED)
            warnings.append(_warning("document_number_ambiguous", name))
        fields[name] = Field(value=_serialize(value), confidence=confidence, source=source)

    if "birth_place" in visual:
        place = visual["birth_place"].value
        fields["birth_place"] = Field(value=_serialize(place), confidence=OCR_ONLY, source="ocr")

    expiry = mrz.expiry_date
    issue = _date(visual, "issue_date")
    printed = _date(visual, "expiry_date")
    if mrz.format is MrzFormat.FR_LEGACY and printed is not None:
        consistent = issue is not None and _validity_years_match(issue, printed)
        confidence = CONFIRMED if consistent else OCR_ONLY
        expiry = printed
        expiry_source: Source = "ocr"
        issued = issue or _add_years(printed, -10)  # ancienne CNI : 10 ans imprimés
        adult = mrz.birth_date is not None and _add_years(mrz.birth_date, 18) <= issued
        if adult and _EXTENSION_START <= issued <= _EXTENSION_END:
            expiry, expiry_source = _add_years(printed, 5), "computed"
            warnings.append(_warning("validity_extended", "expiry_date"))
        fields["expiry_date"] = Field(
            value=expiry.isoformat(), confidence=confidence, source=expiry_source
        )
    if issue is not None:
        consistent = printed is not None and _validity_years_match(issue, printed)
        consistent = consistent or (expiry is not None and _validity_years_match(issue, expiry))
        fields["issue_date"] = Field(
            value=issue.isoformat(),
            confidence=CONFIRMED if consistent else OCR_ONLY,
            source="ocr",
        )
    if expiry is None:
        warnings.append(_warning("expiry_unknown", "expiry_date"))

    matches: CheckStatus = "undetermined" if not compared else "pass" if all(compared) else "fail"
    expired: CheckStatus = (
        "undetermined" if expiry is None else "fail" if expiry < today else "pass"
    )
    checks = [
        Check(code="mrz_checksums", status="pass" if mrz.checksums_valid else "fail"),
        Check(code="mrz_matches_visual", status=matches),
        Check(code="document_expired", status=expired),
    ]
    ordered = {name: fields[name] for name in _FIELD_ORDER if name in fields}
    return ordered, checks, warnings
