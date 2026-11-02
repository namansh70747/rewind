"""Opt-in async start/completion schedule replay, independent of wall-clock delays."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .boundary import Cassette, Divergence, Session, canon
from .redaction import redact

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .boundary import Mode


class RecordedBoundaryError(RuntimeError):
    """Stable captured async failure; original exception type remains evidence."""


class ConcurrentSession(Session):
    """Record task starts and results; replay completion order with a bounded wait.

    Task creation/start order must be stable. Scheduling outside mediated boundaries,
    threads and arbitrary external cancellation timing are not reproduced.
    Producer errors/cancellations have explicit terminal boundaries. Versioned as an opt-in contract.
    """

    def __init__(self, mode: Mode, cassette: Cassette | None = None, timeout: float = 2.0) -> None:
        super().__init__(mode, cassette)
        self._calls = 0
        self._changed = asyncio.Event()
        self.timeout = timeout

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        result = super().mediate(kind, key, request, produce)
        self._changed.set()
        self._changed = asyncio.Event()
        return result

    async def mediate_async(
        self, kind: str, key: str, request: Any, aproduce: Callable[[], Awaitable[Any]]
    ) -> Any:
        call = self._calls
        self._calls += 1
        identity = {"call": call, "kind": kind, "key": key, "request": request}
        self.mediate("async-start", key, identity, lambda: {"call": call})
        if self.mode == "record":
            try:
                value = await aproduce()
            except asyncio.CancelledError:
                self.mediate("async-cancel", key, identity, lambda: {"cancelled": True})
                raise
            except Exception as exc:
                error = redact({"type": type(exc).__name__, "message": str(exc)})
                self.mediate("async-error", key, identity, lambda: error)
                raise RecordedBoundaryError(f"{error['type']}: {error['message']}") from None
            return self.mediate("async-result", key, identity, lambda: value)
        while True:
            if self._cursor >= len(self._recorded):
                raise Divergence(self._cursor, "async completion missing")
            next_event = self._recorded[self._cursor]
            if next_event.kind in {"async-result", "async-error", "async-cancel"} and canon(
                next_event.request
            ) == canon(identity):
                value = self.mediate(next_event.kind, key, identity, lambda: None)
                if next_event.kind == "async-cancel":
                    raise asyncio.CancelledError
                if next_event.kind == "async-error":
                    raise RecordedBoundaryError(f"{value['type']}: {value['message']}")
                return value
            signal = self._changed
            try:
                await asyncio.wait_for(signal.wait(), timeout=self.timeout)
            except TimeoutError as exc:
                raise Divergence(
                    self._cursor, "async schedule changed or incomplete fan-out"
                ) from exc
