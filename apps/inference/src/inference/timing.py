"""Temps passé par étape du traitement, collecté seulement quand un appelant le demande.

    with collect() as timings:
        extract(...)
    timings  # {"file": 0.01, "mrz_ocr": 0.4, ...} en secondes

Sert au benchmark, et en V1 au coût par dossier (spec B8). Sans `collect()`, `stage()` ne
coûte qu'une lecture de variable de contexte.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_current: ContextVar[dict[str, float] | None] = ContextVar("timings", default=None)


@contextmanager
def stage(name: str) -> Iterator[None]:
    timings = _current.get()
    if timings is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[name] = timings.get(name, 0.0) + time.perf_counter() - started


@contextmanager
def collect() -> Iterator[dict[str, float]]:
    timings: dict[str, float] = {}
    token = _current.set(timings)
    try:
        yield timings
    finally:
        _current.reset(token)
