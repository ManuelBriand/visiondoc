from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration par variables d'environnement préfixées `VISIONDOC_`."""

    model_config = SettingsConfigDict(env_prefix="VISIONDOC_")

    # Empreintes SHA-256 (hexadécimal) des clés API acceptées, séparées par des virgules.
    # Les clés elles-mêmes ne sont jamais stockées : `python -m inference.api.keys` en crée une.
    api_key_hashes: str = ""
    max_file_bytes: int = 10 * 1024 * 1024
    # Réglages de PaddleOCR (ADR 0006) : threads de calcul, et plus grand côté de l'image
    # donnée à la détection de texte (vide : pleine résolution, le plus précis).
    cpu_threads: int | None = None
    det_max_side: int | None = None

    def key_hashes(self) -> frozenset[str]:
        return frozenset(h.strip().lower() for h in self.api_key_hashes.split(",") if h.strip())
