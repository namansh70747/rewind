"""Managed MCP v1 SDK transports; replay never connects or starts a subprocess."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any

from ..capture import _active_session
from ..redaction import redact
from ..sources import suppress_sources
from .mcp import MCPToolError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from ..boundary import Session


class MCPClient:
    """Record SDK results as atomic boundaries, including protocol/tool errors.

    Server sampling/elicitation callbacks are not supported. Tool isError results
    remain protocol values; JSON-RPC exceptions become stable MCPToolError values.
    Transport setup/teardown belongs to the surrounding async context manager.
    """

    def __init__(self, session: Session, server: str) -> None:
        self.session, self.server = session, server
        self.initialization: dict[str, Any] = {}
        self._sdk: Any = None
        self._occurrence = 0
        self._open = True

    async def _operation(
        self, method: str, params: dict[str, Any], producer: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        if not self._open:
            raise RuntimeError("MCP client context has closed")
        occurrence = self._occurrence
        self._occurrence += 1

        async def produce() -> dict[str, Any]:
            token = _active_session.set(None)
            try:
                with suppress_sources():
                    try:
                        result = await producer()
                        return {"ok": True, "value": redact(result.model_dump(mode="json"))}
                    except Exception as exc:
                        return dict(
                            redact({"ok": False, "type": type(exc).__name__, "message": str(exc)})
                        )
            finally:
                _active_session.reset(token)

        outcome = await self.session.mediate_async(
            "mcp",
            f"{self.server}/{method}",
            redact({"occurrence": occurrence, "params": params}),
            produce,
        )
        if not outcome["ok"]:
            raise MCPToolError(f"{outcome['type']}: {outcome['message']}")
        return dict(outcome["value"])

    async def list_tools(self, cursor: str | None = None) -> dict[str, Any]:
        return await self._operation(
            "tools/list", {"cursor": cursor}, lambda: self._sdk.list_tools(cursor=cursor)
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._operation(
            "tools/call",
            {"name": name, "arguments": arguments},
            lambda: self._sdk.call_tool(name, arguments),
        )


@asynccontextmanager
async def _managed(
    session: Session,
    server: str,
    transport: str,
    config: dict[str, Any],
    connect: Callable[[AsyncExitStack], Awaitable[Any]],
) -> AsyncIterator[MCPClient]:
    if not server.strip():
        raise ValueError("server identity cannot be empty")
    client = MCPClient(session, server)
    stack = AsyncExitStack()
    try:

        async def initialize() -> Any:
            client._sdk = await connect(stack)
            return await client._sdk.initialize()

        client.initialization = await client._operation(
            "initialize", {"transport": transport, **config}, initialize
        )
        try:
            yield client
        finally:
            client._open = False
    finally:
        token = _active_session.set(None)
        try:
            with suppress_sources():
                await stack.aclose()
        finally:
            _active_session.reset(token)
    # AsyncExitStack is empty in replay: no SDK imports, subprocesses or sockets.


@asynccontextmanager
async def mcp_stdio(
    session: Session,
    server: str,
    command: str,
    args: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> AsyncIterator[MCPClient]:
    """Connect to a trusted local MCP executable during recording only.

    Environment values are never included in the cassette. Executable/arguments
    are redacted and matched. Only execute trusted commands, as with script capture.
    """

    async def connect(stack: AsyncExitStack) -> Any:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        read, write = await stack.enter_async_context(
            stdio_client(StdioServerParameters(command=command, args=args or [], env=env))
        )
        return await stack.enter_async_context(ClientSession(read, write))

    async with _managed(
        session, server, "stdio", {"command": command, "args": args or []}, connect
    ) as client:
        yield client


@asynccontextmanager
async def mcp_http(
    session: Session,
    server: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> AsyncIterator[MCPClient]:
    """Streamable HTTP initialization, session negotiation and cleanup via MCP SDK.

    Headers are credentials/configuration supplied at runtime, never persisted.
    Supported SDK contract is mcp>=1.20,<2, not the incompatible v2 client API.
    """

    async def connect(stack: AsyncExitStack) -> Any:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        http = await stack.enter_async_context(httpx.AsyncClient(headers=headers, timeout=30))
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(url, http_client=http)
        )
        return await stack.enter_async_context(ClientSession(read, write))

    async with _managed(session, server, "streamable-http", {"url": url}, connect) as client:
        yield client
