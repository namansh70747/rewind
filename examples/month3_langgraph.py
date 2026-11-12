"""Month 3: async LangGraph → inspect → fork → verify → viewer traces.

Default uses synthetic HTTP responses. --live uses the selected providers
(default: NVIDIA and Gemini); credentials come from the process environment.
Each provider makes one parent and one allowlisted fork completion request.
All reservation tools are simulated, and are explicitly mocked in the fork.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

import httpx
from langgraph.graph import StateGraph

from flightrecorder.boundary import Cassette, Session
from flightrecorder.fork import afork_run
from flightrecorder.integrations.langgraph import arun_graph
from flightrecorder.interop import write_trace
from flightrecorder.offline import offline_guard
from flightrecorder.policy import SideEffectPolicy, afork_with_policy
from flightrecorder.portable import export_run
from flightrecorder.providers import GEMINI, NVIDIA
from flightrecorder.redaction import RedactionRules, redaction_rules
from flightrecorder.snapshots import SnapshotIndex
from flightrecorder.tools import tool


class State(TypedDict):
    price: int
    explanation: str
    reservation: str


async def scenario(provider, output: Path, live: bool) -> dict:
    key = os.environ.get(provider.key_env, "") if live else ""
    calls = {"http": 0, "reservation": 0}

    @tool(name="month3.quote", mutating=False)
    async def quote() -> int:
        return 720

    @tool(name="month3.reserve", mutating=True)
    async def reserve() -> str:
        calls["reservation"] += 1
        return "simulated reservation"

    async def quote_node(state: State) -> dict:
        return {"price": await quote()}

    async def explain_node(state: State) -> dict:
        def response(request: httpx.Request) -> httpx.Response:
            calls["http"] += 1
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "synthetic explanation"}}]}
            )

        async with httpx.AsyncClient(
            transport=None if live else httpx.MockTransport(response), timeout=120
        ) as client:
            result = await client.post(
                provider.url,
                headers=provider.headers(key),
                json=provider.body(
                    provider.default_model,
                    [
                        {
                            "role": "user",
                            "content": f"Explain in one sentence whether a {state['price']} quote fits a 500 budget.",
                        }
                    ],
                ),
            )
            result.raise_for_status()
            return {"explanation": provider.extract(result.json())}

    async def reserve_node(state: State) -> dict:
        return {"reservation": await reserve()}

    builder = StateGraph(State)
    for name, node in (("quote", quote_node), ("explain", explain_node), ("reserve", reserve_node)):
        builder.add_node(name, node)
    builder.set_entry_point("quote")
    builder.add_edge("quote", "explain")
    builder.add_edge("explain", "reserve")
    builder.set_finish_point("reserve")
    graph = builder.compile()

    async def run(session: Session) -> str:
        return await arun_graph(graph, {"price": 0, "explanation": "", "reservation": ""}, session)

    session = Session("record")
    text = await run(session)
    parent = Cassette(
        session.boundaries, session.chain, text, provider.name, provider.default_model
    )
    target = next(b.seq for b in parent.boundaries if b.key == "month3.quote")
    mocks = {
        ("state", b.key): lambda request: request for b in parent.boundaries if b.kind == "state"
    }
    mocks[("tool", "month3.reserve")] = lambda request: {"ok": True, "value": "mock reservation"}
    http_event = next(b for b in parent.boundaries if b.kind == "http")
    if live:
        child = await afork_with_policy(
            parent,
            run,
            at=target,
            value={"ok": True, "value": 420},
            mocks=mocks,
            policy=SideEffectPolicy(live_allowlist=frozenset({("http", http_event.key)})),
        )
    else:
        mocks[("http", http_event.key)] = lambda request: http_event.response
        child = await afork_run(
            parent, run, at=target, value={"ok": True, "value": 420}, mocks=mocks
        )
    assert calls["reservation"] == 1, "fork invoked mutating tool producer"
    assert json.loads(child.final_output)["price"] == 420
    for cassette, label in ((parent, "parent"), (child, "fork")):
        for _ in range(3):
            replay = Session("replay", cassette)
            with offline_guard() as audit:
                result = await run(replay)
            replay.assert_fully_consumed()
            assert not audit.blocked_operations
            assert result == cassette.final_output and replay.chain == cassette.fingerprint
        index = SnapshotIndex(cassette)
        for at in range(len(cassette.boundaries)):
            assert index.at(at)["replayed_events"] < index.interval
        export_run(cassette, output / f"{provider.name}-{label}.rewind.json")
        for format in ("perfetto", "otlp", "otlp-protobuf"):
            write_trace(cassette, output / f"{provider.name}-{label}.{format}", format)
    return {
        "provider": provider.name,
        "model": provider.default_model,
        "source": "live" if live else "synthetic",
        "offline_replays": 6,
        "mutating_fork_calls": calls["reservation"] - 1,
        "boundaries": len(parent.boundaries),
        "parent": parent.fingerprint,
        "fork": child.fingerprint,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".rewind/month3"))
    parser.add_argument(
        "--provider",
        choices=("nvidia", "gemini"),
        action="append",
        help="Select a provider; repeat for both (default: both)",
    )
    parser.add_argument("--model", help="Override model when exactly one provider is selected")
    args = parser.parse_args()
    selected = [p for p in (NVIDIA, GEMINI) if not args.provider or p.name in args.provider]
    if args.model:
        if len(selected) != 1:
            parser.error("--model requires exactly one --provider")
        selected = [replace(selected[0], default_model=args.model)]
    if args.live:
        missing = [p.key_env for p in selected if not os.environ.get(p.key_env)]
        if missing:
            parser.error("Configure credentials in the environment: " + ", ".join(missing))
    if args.output.exists():
        parser.error("Choose a new output directory to preserve prior evidence")
    args.output.mkdir(parents=True)
    literals = tuple(os.environ[p.key_env] for p in selected if args.live)
    with redaction_rules(RedactionRules(literals=literals)):
        reports = [asyncio.run(scenario(p, args.output, args.live)) for p in selected]
    (args.output / "report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
