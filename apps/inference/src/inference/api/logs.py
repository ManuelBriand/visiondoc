"""Journaux JSON sur une ligne : uniquement des métadonnées techniques, jamais de données."""

import json
import logging

_FIELDS = ("request_id", "method", "path", "status", "duration_ms", "error_code", "exception")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update({key: getattr(record, key) for key in _FIELDS if hasattr(record, key)})
        return json.dumps(payload, ensure_ascii=False)


def configure() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("inference")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
