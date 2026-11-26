"""Explicit tool boundaries with structured outcomes, safe redaction and classification."""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any

from .capture import _active_session
from .redaction import redact
from .sources import suppress_sources

if TYPE_CHECKING:
    from collections.abc import Callable


class RecordedToolError(RuntimeError):
    """A captured tool failure; original type is evidence, not executable code."""


TOOL_MANIFEST: dict[str, dict[str, Any]] = {}


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    mutating: bool = True,
) -> Callable[..., Any]:
    """Mark an atomic tool. Unknown tools default to mutating for fork policy.

    Use ``@tool`` or ``@tool(name=..., mutating=...)``. Nested I/O inside the
    producer belongs to this atomic boundary and is not separately captured.
    Errors replay as RecordedToolError in both modes.
    """

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        label = name or f"{func.__module__}.{func.__qualname__}"
        TOOL_MANIFEST[label] = {"mutating": mutating}

        def unpack(outcome: Any) -> Any:
            if outcome["ok"]:
                return outcome["value"]
            raise RecordedToolError(f"{outcome['type']}: {outcome['message']}")

        @functools.wraps(func)
        def sync(*args: Any, **kwargs: Any) -> Any:
            session = _active_session.get()
            if session is None:
                return func(*args, **kwargs)

            def produce() -> Any:
                token = _active_session.set(None)
                try:
                    try:
                        with suppress_sources():
                            return {"ok": True, "value": redact(func(*args, **kwargs))}
                    except Exception as exc:
                        return redact(
                            {"ok": False, "type": type(exc).__name__, "message": str(exc)}
                        )
                finally:
                    _active_session.reset(token)

            return unpack(
                session.mediate("tool", label, redact({"args": args, "kwargs": kwargs}), produce)
            )

        @functools.wraps(func)
        async def asynchronous(*args: Any, **kwargs: Any) -> Any:
            session = _active_session.get()
            if session is None:
                return await func(*args, **kwargs)

            async def produce() -> Any:
                token = _active_session.set(None)
                try:
                    try:
                        with suppress_sources():
                            return {"ok": True, "value": redact(await func(*args, **kwargs))}
                    except Exception as exc:
                        return redact(
                            {"ok": False, "type": type(exc).__name__, "message": str(exc)}
                        )
                finally:
                    _active_session.reset(token)

            return unpack(
                await session.mediate_async(
                    "tool", label, redact({"args": args, "kwargs": kwargs}), produce
                )
            )

        return asynchronous if inspect.iscoroutinefunction(func) else sync

    if fn is not None:
        return decorate(fn)
    return decorate
