"""Explicit agent API, no network or API keys: python examples/session_agent.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flightrecorder import Cassette, Session, verify
from flightrecorder.fork import fork_run

if TYPE_CHECKING:
    import httpx


def agent(session: Session, inner: httpx.BaseTransport | None) -> str:
    value = session.mediate("tool", "temperature", {"unit": "C"}, lambda: 45)
    return "Cooling required" if value > 35 else "Temperature normal"


session = Session("record")
output = agent(session, None)
parent = Cassette(session.boundaries, session.chain, output)
child = fork_run(parent, agent, at=0, value=25)
print("Original:", parent.final_output)
print("What-if:", child.final_output)
print(verify(child, agent, n=10))
