"""Actual local SDK server for lifecycle integration tests; no external services."""

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

transport, marker = sys.argv[1:3]
server = FastMCP("rewind-test", port=int(sys.argv[3]) if len(sys.argv) > 3 else 8000)


@server.tool()
def add(a: int, b: int) -> int:
    with Path(marker).open("a") as f:
        f.write("called\n")
    return a + b


@server.tool()
def fail() -> str:
    raise ValueError("test tool failure")


if __name__ == "__main__":
    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "streamable-http":
        server.run(transport="streamable-http")
    else:
        raise ValueError("unsupported test transport")
