"""Réponse de l'extraction, au format du contrat d'API (spec A3)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

DocumentType = Literal["fr_id_card_2021", "fr_id_card_legacy", "fr_passport"]
Source = Literal["mrz", "ocr", "computed"]
CheckStatus = Literal["pass", "fail", "undetermined"]


class Field(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str | list[str]  # dates en ISO 8601
    confidence: float
    source: Source


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    status: CheckStatus


class WarningItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    field: str | None = None
    message: str


class MrzSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw: list[str]
    format: str
    checksums_valid: bool


class Extraction(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_type: DocumentType
    issuing_country: str
    fields: dict[str, Field]
    mrz: MrzSummary
    checks: list[Check]
    warnings: list[WarningItem]
    processing_ms: int
