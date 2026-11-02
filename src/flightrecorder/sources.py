"""Scoped, opt-in Python time/UUID/random shims. Never patch event-loop monotonic time."""

from __future__ import annotations

import os
import random
import time
import uuid
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from .redaction import redact

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .boundary import Session

_busy: ContextVar[bool] = ContextVar("rewind_source_busy", default=False)


@contextmanager
def suppress_sources() -> Iterator[None]:
    token = _busy.set(True)
    try:
        yield
    finally:
        _busy.reset(token)


@contextmanager
def deterministic_sources(session: Session) -> Iterator[None]:
    """Scope to trusted single-process agents. Cached aliases and Random instances excluded."""

    def wrap(kind: str, key: str, original: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            if _busy.get():
                return original(*args, **kwargs)
            with suppress_sources():
                return session.mediate(
                    kind,
                    key,
                    {"args": list(args), "kwargs": kwargs},
                    lambda: original(*args, **kwargs),
                )

        return call

    with ExitStack() as stack:
        stack.enter_context(patch.object(time, "time", wrap("clock", "time", time.time)))
        for name in ("random", "randint", "uniform", "choice"):
            stack.enter_context(
                patch.object(random, name, wrap("rng", name, getattr(random, name)))
            )
        original = uuid.uuid4
        generate = wrap("uuid", "uuid4", lambda: str(original()))
        stack.enter_context(patch.object(uuid, "uuid4", lambda: uuid.UUID(generate())))
        yield


def config_read(session: Session, name: str, default: str = "") -> str:
    """Capture an explicit non-secret environment/config read, sanitized before delivery."""
    if any(word in name.lower() for word in ("key", "token", "password", "secret")):
        raise ValueError("credential environment variables must not be recorded as configuration")
    return str(
        session.mediate(
            "config", name, {"default": default}, lambda: redact(os.environ.get(name, default))
        )
    )
