"""Erreurs métier du service, alignées sur les codes de l'API (spec A3)."""

from typing import Literal

ErrorCode = Literal[
    "unsupported_document",
    "image_unreadable",
    "mrz_not_found",
    "file_too_large",
    "invalid_format",
    "unauthorized",
]

UnreadableCause = Literal["blurry", "too_dark", "overexposed", "too_small", "cropped"]

UNREADABLE_MESSAGES: dict[UnreadableCause, str] = {
    "blurry": "La photo est floue : reprenez-la en tenant le téléphone immobile.",
    "too_dark": "La photo est trop sombre : reprenez-la dans un endroit plus éclairé.",
    "overexposed": "La photo est surexposée : évitez les reflets et la lumière directe.",
    "too_small": "La photo est trop petite : rapprochez-vous du document.",
    "cropped": "Le document est coupé : cadrez-le entièrement sur la photo.",
}


class ExtractionError(Exception):
    """Erreur renvoyée telle quelle au client. Le message ne contient aucune donnée extraite."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


class ImageUnreadableError(ExtractionError):
    def __init__(self, cause: UnreadableCause) -> None:
        super().__init__("image_unreadable", UNREADABLE_MESSAGES[cause])
        self.cause: UnreadableCause = cause
