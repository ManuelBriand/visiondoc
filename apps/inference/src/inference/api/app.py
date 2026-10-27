"""Application FastAPI : `POST /v1/extract` et `GET /health` (spec A3).

Journaux : identifiant de requête, route, statut, durée et code d'erreur. Jamais d'image,
de donnée extraite ni de message d'exception (qui pourrait en contenir).
"""

import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import inference
from inference.api.keys import is_valid
from inference.api.settings import Settings
from inference.api.upload import InvalidRequestError, read_files
from inference.errors import ErrorCode, ExtractionError
from inference.ocr.mrz_reader import LineRecognizer
from inference.ocr.text_engine import TextEngine
from inference.pipeline.extract import extract
from inference.pipeline.models import Extraction

logger = logging.getLogger("inference.api")

STATUS: dict[ErrorCode, int] = {
    "unsupported_document": 422,
    "image_unreadable": 422,
    "mrz_not_found": 422,
    "file_too_large": 413,
    "invalid_format": 415,
    "unauthorized": 401,
}

_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
        }
    },
}


def _error_responses() -> dict[int | str, dict[str, Any]]:
    """Documentation OpenAPI des erreurs, regroupées par statut HTTP."""
    by_status: dict[int, list[str]] = {}
    codes: list[tuple[str, int]] = [*STATUS.items(), ("invalid_request", 400)]
    for code, status in codes:
        by_status.setdefault(status, []).append(code)
    return {
        status: {
            "description": ", ".join(names),
            "content": {"application/json": {"schema": _ERROR_SCHEMA}},
        }
        for status, names in sorted(by_status.items())
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(
    settings: Settings,
    recognizer: LineRecognizer,
    engine: TextEngine,
    models: dict[str, str],
) -> FastAPI:
    """`models` décrit les modèles chargés, pour `/health`."""
    app = FastAPI(
        title="Visiondoc — extraction de pièces d'identité",
        version=inference.__version__,
        description="CNI et passeport français : données extraites, MRZ validée, confiance.",
    )
    key_hashes = settings.key_hashes()
    # Les modèles PaddleOCR ne sont pas sûrs en multithread : une extraction à la fois par
    # processus ; on monte en charge avec plusieurs processus ou conteneurs.
    model_lock = threading.Lock()

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex
        request.state.error_code = None
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Capturée ici pour ne jamais être relancée : le serveur journaliserait sinon
            # la trace et le message, qui pourraient contenir des données.
            request.state.error_code = "internal_error"
            logger.error("unexpected_error", extra={"exception": type(exc).__name__})
            response = _error(500, "internal_error", "Erreur interne.")
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "error_code": request.state.error_code,
            },
        )
        return response

    @app.exception_handler(ExtractionError)
    async def on_extraction_error(request: Request, exc: ExtractionError) -> JSONResponse:
        request.state.error_code = exc.code
        return _error(STATUS[exc.code], exc.code, exc.message)

    @app.exception_handler(InvalidRequestError)
    async def on_invalid_request(request: Request, exc: InvalidRequestError) -> JSONResponse:
        request.state.error_code = "invalid_request"
        return _error(400, "invalid_request", str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        request.state.error_code = code
        return _error(exc.status_code, code, str(exc.detail))

    def require_api_key(request: Request) -> None:
        scheme, _, key = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not key or not is_valid(key.strip(), key_hashes):
            raise ExtractionError("unauthorized", "Clé API absente ou invalide.")

    def run_extraction(front: bytes, back: bytes | None) -> Extraction:
        with model_lock:
            return extract(front, back, recognizer, engine)

    @app.post(
        "/v1/extract",
        response_model=Extraction,
        dependencies=[Depends(require_api_key)],
        responses=_error_responses(),
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["front"],
                            "properties": {
                                "front": {"type": "string", "format": "binary"},
                                "back": {"type": "string", "format": "binary"},
                            },
                        }
                    }
                },
            }
        },
    )
    async def extract_document(request: Request) -> Extraction:
        """Une ou deux faces (JPEG, PNG ou PDF d'une page, 10 Mo maximum chacune)."""
        files = await read_files(request, ("front", "back"), settings.max_file_bytes)
        if "front" not in files:
            raise InvalidRequestError("Le champ « front » est obligatoire.")
        return await run_in_threadpool(run_extraction, files["front"], files.get("back"))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "engine": {"version": inference.__version__, "models": models}}

    return app
