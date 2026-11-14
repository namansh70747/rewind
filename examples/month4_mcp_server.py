"""Local MCP fixture with real stdio/HTTP transports and observable tool effects."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
parser.add_argument("--marker", type=Path, required=True)
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
server = FastMCP("rewind-month4", port=args.port)


@server.tool()
async def add(a: int, b: int, delay: float = 0) -> int:
    await asyncio.sleep(delay)
    with args.marker.open("a") as stream:
        stream.write("called\n")
    return a + b


@server.tool()
def fail() -> str:
    raise ValueError("controlled tool failure")


if __name__ == "__main__":
    server.run(transport=args.transport)
