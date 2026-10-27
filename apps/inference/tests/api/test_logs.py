import json
import logging

from inference.api.logs import JsonFormatter


def test_json_line_keeps_only_known_metadata() -> None:
    record = logging.LogRecord("inference.api", logging.INFO, "f", 1, "request", None, None)
    record.__dict__.update({"status": 200, "path": "/v1/extract", "secret": "MARTIN"})
    line = json.loads(JsonFormatter().format(record))
    assert line["event"] == "request"
    assert line["status"] == 200
    assert line["path"] == "/v1/extract"
    assert "secret" not in line
