"""MCP tools/call JSON-RPC boundary adapter with stable per-server occurrence IDs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..redaction import redact

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..boundary import Session


class MCPToolError(RuntimeError):
    pass


class MCPRecorder:
    """Wrap an initialized transport's request/response exchange.

    Connection/initialization lifecycle belongs to the host MCP client. During
    replay exchange is never invoked; server identity and call ordinal must match.
    """

    def __init__(
        self,
        session: Session,
        server: str,
        exchange: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self.session, self.server, self.exchange = session, server, exchange
        self.occurrence = 0

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        occurrence = self.occurrence
        self.occurrence += 1
        frame = {
            "jsonrpc": "2.0",
            "id": occurrence,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }

        async def produce() -> Any:
            if self.exchange is None:
                raise RuntimeError("recording requires an initialized MCP exchange")
            response = await self.exchange(frame)
            if response.get("id") != occurrence or response.get("jsonrpc") != "2.0":
                raise ValueError("MCP JSON-RPC response identity mismatch")
            return redact(response)

        response = await self.session.mediate_async(
            "mcp", f"{self.server}/{name}", redact(frame), produce
        )
        if "error" in response:
            raise MCPToolError(str(response["error"]))
        if "result" not in response:
            raise ValueError("MCP response has neither result nor error")
        return response["result"]
