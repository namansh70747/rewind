"""Observe public MCP SDK stream messages without changing transport semantics."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from anyio import EndOfStream

from ..redaction import redact


class WireTap:
    def __init__(self) -> None:
        self.operation: ContextVar[int | None] = ContextVar("mcp_operation", default=None)
        self.owners: dict[Any, int] = {}
        self.frames: dict[int, list[dict[str, Any]]] = {}

    def observe(self, message: Any, direction: str) -> None:
        if isinstance(message, Exception):
            return
        root = getattr(message.message, "root", message.message)
        frame = redact(root.model_dump(mode="json", by_alias=True, exclude_none=True))
        identity = frame.get("id")
        if direction == "request":
            if "method" not in frame:
                return  # A reply to a server-initiated request is not our client request.
            owner = self.operation.get()
            if owner is not None and identity is not None:
                self.owners[identity] = owner
        else:
            if "method" in frame:
                return  # Server notifications/requests are outside tools/call responses.
            owner = self.owners.pop(identity, None)
        if owner is not None and identity is not None:
            self.frames.setdefault(owner, []).append({"direction": direction, "frame": frame})

    def finish(self, occurrence: int) -> list[dict[str, Any]]:
        # A disconnected request may never receive a terminal response.
        self.owners = {key: owner for key, owner in self.owners.items() if owner != occurrence}
        return self.frames.pop(occurrence, [])


class TappedStream:
    """Duck-type the SDK's public object streams, including cloned streams."""

    def __init__(self, stream: Any, tap: WireTap, direction: str) -> None:
        self.stream, self.tap, self.direction = stream, tap, direction

    async def send(self, message: Any) -> None:
        self.tap.observe(message, self.direction)
        await self.stream.send(message)

    async def receive(self) -> Any:
        message = await self.stream.receive()
        self.tap.observe(message, self.direction)
        return message

    def __aiter__(self) -> TappedStream:
        return self

    async def __anext__(self) -> Any:
        try:
            return await self.receive()
        except EndOfStream:
            raise StopAsyncIteration from None

    async def __aenter__(self) -> TappedStream:
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> Any:
        return await self.stream.__aexit__(*args)

    async def aclose(self) -> None:
        await self.stream.aclose()

    def clone(self) -> TappedStream:
        return TappedStream(self.stream.clone(), self.tap, self.direction)
