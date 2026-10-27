import logging
import random
import tempfile
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from cv2.typing import MatLike
from fastapi.testclient import TestClient

from inference.api import app as app_module
from inference.api.app import create_app
from inference.api.keys import fingerprint, is_valid, new_key
from inference.api.settings import Settings
from inference.errors import ErrorCode, ExtractionError, ImageUnreadableError
from inference.ocr.text_engine import TextBox
from inference.pipeline.models import Extraction, MrzSummary
from inference.synth.documents import Fonts, make_specimen

KEY = "vd_test-key"
AUTH = {"Authorization": f"Bearer {KEY}"}
MODELS = {"mrz_recognition": "fake", "text_detection": "fake", "text_recognition": "fake"}

CANNED = Extraction(
    document_type="fr_passport",
    issuing_country="FRA",
    fields={},
    mrz=MrzSummary(raw=["P<FRA", "X"], format="TD3", checksums_valid=True),
    checks=[],
    warnings=[],
    processing_ms=12,
)


class NoRecognizer:
    def recognize(self, images: Sequence[MatLike]) -> list[str]:
        raise AssertionError("non appelé")


class NoEngine:
    def read(self, image: MatLike) -> list[TextBox]:
        return []


def make_client(**settings: Any) -> TestClient:
    config = Settings(api_key_hashes=fingerprint(KEY), **settings)
    return TestClient(create_app(config, NoRecognizer(), NoEngine(), MODELS))


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, bytes | None]]:
    seen: list[tuple[bytes, bytes | None]] = []

    def fake_extract(front: bytes, back: bytes | None, *_: object) -> Extraction:
        seen.append((front, back))
        return CANNED

    monkeypatch.setattr(app_module, "extract", fake_extract)
    return seen


def raising(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fake_extract(*_: object) -> Extraction:
        raise error

    monkeypatch.setattr(app_module, "extract", fake_extract)


def post(client: TestClient, **files: bytes) -> Any:
    return client.post("/v1/extract", headers=AUTH, files={k: (k, v) for k, v in files.items()})


def test_health_needs_no_key() -> None:
    response = make_client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "engine": {"version": "0.1.0", "models": MODELS}}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": KEY}, {"Authorization": "Basic x"}],
)
def test_unauthorized(headers: dict[str, str], calls: list[object]) -> None:
    response = make_client().post("/v1/extract", headers=headers, files={"front": ("f", b"x")})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert calls == []


def test_no_configured_key_rejects_everything(calls: list[object]) -> None:
    client = TestClient(create_app(Settings(), NoRecognizer(), NoEngine(), MODELS))
    response = client.post("/v1/extract", headers=AUTH, files={"front": ("f", b"x")})
    assert response.status_code == 401


def test_success(calls: list[tuple[bytes, bytes | None]]) -> None:
    response = post(make_client(), front=b"recto", back=b"verso")
    assert response.status_code == 200
    assert response.json() == CANNED.model_dump()
    assert len(response.headers["X-Request-ID"]) == 32
    assert calls == [(b"recto", b"verso")]


def test_back_is_optional_and_unknown_parts_are_ignored(
    calls: list[tuple[bytes, bytes | None]],
) -> None:
    response = post(make_client(), front=b"recto", other=b"ignored")
    assert response.status_code == 200
    assert calls == [(b"recto", None)]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"files": {"back": ("b", b"verso")}}, "front"), ({"json": {"front": "x"}}, "multipart")],
)
def test_invalid_request(kwargs: dict[str, Any], message: str, calls: list[object]) -> None:
    response = make_client().post("/v1/extract", headers=AUTH, **kwargs)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert message in response.json()["error"]["message"]


def test_duplicate_field_is_rejected(calls: list[object]) -> None:
    files = [("front", ("a", b"1")), ("front", ("b", b"2"))]
    response = make_client().post("/v1/extract", headers=AUTH, files=files)
    assert response.status_code == 400


def test_malformed_multipart(calls: list[object]) -> None:
    headers = {**AUTH, "Content-Type": "multipart/form-data; boundary=xyz"}
    response = make_client().post("/v1/extract", headers=headers, content=b"--xyz\r\ngarbage")
    assert response.status_code == 400


def test_file_too_large_by_declared_length(calls: list[object]) -> None:
    response = post(make_client(max_file_bytes=1000), front=b"x" * 200_000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert calls == []


def test_file_too_large_while_streaming(calls: list[object]) -> None:
    def body() -> Iterator[bytes]:
        yield b'--b\r\nContent-Disposition: form-data; name="front"; filename="f"\r\n\r\n'
        for _ in range(20):
            yield b"x" * 100
        yield b"\r\n--b--\r\n"

    headers = {**AUTH, "Content-Type": "multipart/form-data; boundary=b"}
    response = make_client(max_file_bytes=1000).post("/v1/extract", headers=headers, content=body())
    assert response.status_code == 413
    assert calls == []


def test_upload_never_touches_disk(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[bytes, bytes | None]]
) -> None:
    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("écriture sur disque")

    monkeypatch.setattr(tempfile, "SpooledTemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryFile", forbidden)
    payload = bytes(range(256)) * 8192  # 2 Mo
    response = post(make_client(), front=payload)
    assert response.status_code == 200
    assert calls[0][0] == payload


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ExtractionError("unsupported_document", "m"), 422, "unsupported_document"),
        (ImageUnreadableError("blurry"), 422, "image_unreadable"),
        (ExtractionError("mrz_not_found", "m"), 422, "mrz_not_found"),
        (ExtractionError("invalid_format", "m"), 415, "invalid_format"),
        (ExtractionError("file_too_large", "m"), 413, "file_too_large"),
    ],
)
def test_extraction_errors(
    monkeypatch: pytest.MonkeyPatch, error: ExtractionError, status: int, code: ErrorCode
) -> None:
    raising(monkeypatch, error)
    response = post(make_client(), front=b"x")
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": error.message}}


def test_real_file_check_rejects_text() -> None:
    response = post(make_client(), front=b"not an image at all")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "invalid_format"


def test_unexpected_error_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    raising(monkeypatch, RuntimeError("MARTIN 1990-04-12"))
    with caplog.at_level(logging.INFO, logger="inference"):
        response = post(make_client(), front=b"x")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Erreur interne."}}
    assert "MARTIN" not in caplog.text
    error = next(r for r in caplog.records if r.getMessage() == "unexpected_error")
    assert error.__dict__["exception"] == "RuntimeError"
    assert all("MARTIN" not in str(r.__dict__) for r in caplog.records)


def test_request_log_contains_only_metadata(
    calls: list[object], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="inference"):
        post(make_client(), front=b"SECRET-IMAGE-BYTES")
    record = next(r for r in caplog.records if r.getMessage() == "request")
    assert record.__dict__["status"] == 200
    assert record.__dict__["path"] == "/v1/extract"
    assert "SECRET" not in caplog.text


def test_not_found_uses_error_format() -> None:
    response = make_client().get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_openapi_documents_multipart_and_errors() -> None:
    spec = make_client().get("/openapi.json").json()
    operation = spec["paths"]["/v1/extract"]["post"]
    schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert schema["required"] == ["front"]
    assert {"200", "400", "401", "413", "415", "422"} <= set(operation["responses"])


def test_end_to_end_with_real_pipeline(fonts: Fonts) -> None:
    specimen = make_specimen("fr_passport", random.Random(1), fonts)

    class Truth:
        def recognize(self, images: Sequence[MatLike]) -> list[str]:
            return list(specimen.mrz)

    config = Settings(api_key_hashes=fingerprint(KEY))
    client = TestClient(create_app(config, Truth(), NoEngine(), MODELS))
    response = post(client, front=specimen.image)
    assert response.status_code == 200
    body = response.json()
    assert body["document_type"] == "fr_passport"
    assert body["fields"]["document_number"] == {
        "value": specimen.identity.document_number,
        "confidence": 1.0,
        "source": "mrz",
    }
    assert body["mrz"]["format"] == "TD3"
    assert [c["code"] for c in body["checks"]] == [
        "mrz_checksums",
        "mrz_matches_visual",
        "document_expired",
    ]


def test_keys() -> None:
    key = new_key()
    assert key.startswith("vd_") and len(key) > 40
    assert is_valid(key, frozenset({fingerprint(key), "0" * 64}))
    assert not is_valid(key + "x", frozenset({fingerprint(key)}))
    assert not is_valid(key, frozenset())
    assert Settings(api_key_hashes=" ABC , def,").key_hashes() == {"abc", "def"}


def test_performance_settings_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISIONDOC_CPU_THREADS", "2")
    monkeypatch.setenv("VISIONDOC_DET_MAX_SIDE", "736")
    settings = Settings()
    assert (settings.cpu_threads, settings.det_max_side) == (2, 736)
    assert Settings(_env_file=None).max_file_bytes == 10 * 1024 * 1024
