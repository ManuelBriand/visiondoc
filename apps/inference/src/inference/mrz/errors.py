from typing import Literal

MrzErrorCode = Literal[
    "invalid_characters",
    "invalid_length",
    "unsupported_format",
    "invalid_field",
]


class MrzError(ValueError):
    """MRZ illisible ou non prise en charge.

    Le message ne contient jamais le contenu de la MRZ : il peut finir dans des logs.
    """

    def __init__(self, code: MrzErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: MrzErrorCode = code
