"""MCP fleet lifecycle registry over the supported SDK transport seams."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .mcp_client import MCPClient, mcp_http, mcp_stdio

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ..boundary import Session


@dataclass(frozen=True)
class MCPServer:
    name: str
    transport: str
    address: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None


class MCPFleet:
    def __init__(self, clients: dict[str, MCPClient]) -> None:
        self.clients = clients

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if server not in self.clients:
            raise ValueError(f"unknown MCP server: {server}")
        return await self.clients[server].call_tool(tool, arguments)

    async def gather(self, calls: list[tuple[str, str, dict[str, Any]]]) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.call(*call) for call in calls)))


@asynccontextmanager
async def open_fleet(session: Session, servers: list[MCPServer]) -> AsyncIterator[MCPFleet]:
    names = [server.name for server in servers]
    if not servers or any(not name.strip() for name in names) or len(set(names)) != len(names):
        raise ValueError("fleet requires unique nonempty server identities")
    if any(server.transport not in {"stdio", "streamable-http"} for server in servers):
        raise ValueError("MCP transport must be stdio or streamable-http")
    if any(not server.address.strip() for server in servers):
        raise ValueError("MCP server address cannot be empty")
    async with AsyncExitStack() as stack:
        clients = {}
        # Stable lifecycle order; tool calls can fan out through ConcurrentSession.
        for spec in servers:
            context = (
                mcp_stdio(session, spec.name, spec.address, spec.args, env=spec.env)
                if spec.transport == "stdio"
                else mcp_http(session, spec.name, spec.address, headers=spec.headers)
            )
            clients[spec.name] = await stack.enter_async_context(context)
        yield MCPFleet(clients)
