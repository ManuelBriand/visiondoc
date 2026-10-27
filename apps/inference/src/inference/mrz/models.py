from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

Sex = Literal["M", "F"]


class MrzFormat(StrEnum):
    TD1 = "TD1"  # 3 x 30 : nouvelle CNI (2021)
    TD3 = "TD3"  # 2 x 44 : passeport
    FR_LEGACY = "FR_LEGACY"  # 2 x 36 : ancienne CNI, structure propre à la France


class MrzResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: MrzFormat
    document_code: str
    issuing_country: str
    last_name: str
    first_names: tuple[str, ...]
    document_number: str
    nationality: str | None
    birth_date: date | None
    sex: Sex | None
    expiry_date: date | None
    optional_data: str
    checks: dict[str, bool]
    # Positions (ligne, colonne) corrigées par la normalisation des champs numériques.
    corrections: tuple[tuple[int, int], ...] = ()
    raw: tuple[str, ...]

    @property
    def checksums_valid(self) -> bool:
        return all(self.checks.values())
