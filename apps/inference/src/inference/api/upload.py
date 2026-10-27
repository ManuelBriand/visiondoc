"""Lecture du corps `multipart/form-data` en flux, entièrement en mémoire.

Le parseur de Starlette bascule sur un fichier temporaire au-delà de 1 Mo : une image
finirait sur disque, ce que la spec interdit. Ici, chaque partie est accumulée en mémoire
et la taille est contrôlée pendant la réception : un envoi trop gros est coupé sans être
lu en entier.
"""

from dataclasses import dataclass, field

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import Request

from inference.errors import ExtractionError

_MAX_PARTS = 4
_OVERHEAD_BYTES = 64 * 1024  # en-têtes et délimiteurs des parties


class InvalidRequestError(Exception):
    """Requête mal formée (hors des codes métier du contrat)."""


@dataclass
class _State:
    max_part_bytes: int
    parts: dict[str, bytearray] = field(default_factory=dict)
    header_field: bytearray = field(default_factory=bytearray)
    header_value: bytearray = field(default_factory=bytearray)
    current: str | None = None
    count: int = 0


def _too_large() -> ExtractionError:
    return ExtractionError("file_too_large", "Le fichier dépasse 10 Mo.")


async def read_files(
    request: Request, names: tuple[str, ...], max_part_bytes: int
) -> dict[str, bytes]:
    content_type, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise InvalidRequestError("Le corps doit être en multipart/form-data.")
    max_body = len(names) * max_part_bytes + _OVERHEAD_BYTES
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_body:
        raise _too_large()

    state = _State(max_part_bytes=max_part_bytes)

    def on_part_begin() -> None:
        state.count += 1
        state.current = None
        if state.count > _MAX_PARTS:
            raise InvalidRequestError("Trop de parties dans la requête.")

    def on_header_field(data: bytes, start: int, end: int) -> None:
        state.header_field += data[start:end]

    def on_header_value(data: bytes, start: int, end: int) -> None:
        state.header_value += data[start:end]

    def on_header_end() -> None:
        if bytes(state.header_field).lower() == b"content-disposition":
            _, options = parse_options_header(bytes(state.header_value))
            name = options.get(b"name", b"").decode("utf-8", "replace")
            if name in names:
                if name in state.parts:
                    raise InvalidRequestError("Champ fourni deux fois.")
                state.current = name
                state.parts[name] = bytearray()
        state.header_field.clear()
        state.header_value.clear()

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if state.current is None:
            return  # partie inconnue : ignorée, mais comptée dans la taille totale
        buffer = state.parts[state.current]
        if len(buffer) + (end - start) > state.max_part_bytes:
            raise _too_large()
        buffer += data[start:end]

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_part_data": on_part_data,
        },
    )
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_body:
                raise _too_large()
            parser.write(chunk)
        parser.finalize()
    except MultipartParseError as exc:
        raise InvalidRequestError("Corps multipart mal formé.") from exc
    return {name: bytes(data) for name, data in state.parts.items() if data}
