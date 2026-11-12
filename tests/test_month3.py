"""Month 3 regressions: async fork policy, navigation, providers and script CLI."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flightrecorder.boundary import Cassette, Divergence, Session
from flightrecorder.cli import app
from flightrecorder.fork import afork_run
from flightrecorder.inspection import state_at
from flightrecorder.policy import SideEffectPolicy, afork_with_policy
from flightrecorder.providers import GEMINI
from flightrecorder.scripts import record_script, verify_script
from flightrecorder.store import RunStore


def test_async_policy_prefix_live_and_mutating_mock() -> None:
    async def scenario() -> None:
        effects: list[str] = []

        async def produce(label: str, value: Any) -> Any:
            effects.append(label)
            await asyncio.sleep(0)
            return value

        async def run(s: Session) -> str:
            await s.mediate_async("tool", "prefix", None, lambda: produce("prefix", 1))
            price = await s.mediate_async("tool", "quote", None, lambda: produce("quote", 720))
            explanation = await s.mediate_async(
                "http", "explain", {"price": price}, lambda: produce("explain", f"price={price}")
            )
            booking = await s.mediate_async(
                "tool", "reserve", price, lambda: produce("reserve", "real booking")
            )
            return json.dumps([price, explanation, booking])

        recorded = Session("record")
        output = await run(recorded)
        parent = Cassette(recorded.boundaries, recorded.chain, output)
        effects.clear()
        mocks = {("tool", "reserve"): lambda request: "mock booking"}
        policy = SideEffectPolicy(live_allowlist=frozenset({("http", "explain")}))
        child = await afork_with_policy(parent, run, at=1, value=420, mocks=mocks, policy=policy)
        assert effects == ["explain"]
        assert json.loads(child.final_output) == [420, "price=420", "mock booking"]
        assert child.boundaries[0] == parent.boundaries[0]
        assert parent.boundaries[1].response == 720
        assert child.metadata["counterfactual"]
        assert child.metadata["parent_fingerprint"] == parent.fingerprint
        replay = Session("replay", child)
        assert await run(replay) == child.final_output
        replay.assert_fully_consumed()
        assert replay.chain == child.fingerprint
        assert effects == ["explain"]
        # Classification cannot authorize I/O, and an explicit mock wins over live.
        with pytest.raises(Divergence, match="explicit mock"):
            await afork_with_policy(
                parent,
                run,
                at=1,
                value=420,
                mocks=mocks,
                policy=SideEffectPolicy(read_only=frozenset({("http", "explain")})),
            )
        mocks[("http", "explain")] = lambda request: "mock explanation"
        await afork_with_policy(parent, run, at=1, value=420, mocks=mocks, policy=policy)
        assert effects == ["explain"]
        await afork_run(parent, run, at=1, value=420, mocks=mocks)
        assert effects == ["explain"]

    asyncio.run(scenario())


def test_async_fork_cancellation_restores_policy() -> None:
    from flightrecorder.policy import PolicyForkSession

    async def scenario() -> None:
        recorded = Session("record")
        recorded.mediate("tool", "quote", None, lambda: 1)
        parent = Cassette(recorded.boundaries, recorded.chain)
        session = PolicyForkSession(parent, 0, 2, {})
        session.policy = SideEffectPolicy(live_allowlist=frozenset({("http", "live")}))
        session.mediate("tool", "quote", None, lambda: None)

        async def cancel() -> Any:
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await session.mediate_async("http", "live", None, cancel)
        assert not session._in_flight
        assert not session.mocks
        assert len(session.boundaries) == 1

    asyncio.run(scenario())


def test_show_at_and_general_fork_cli(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text("""from flightrecorder.tools import tool
@tool(name="quote", mutating=False)
def quote():
    return 720
print(quote())
""")
    cassette = record_script(script)
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    rid = store.save(cassette)
    store.close()
    value, mocks = tmp_path / "value.json", tmp_path / "mocks.json"
    value.write_text('{"ok": true, "value": 420}')
    mocks.write_text("{}")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fork",
            rid,
            "--source",
            str(script),
            "--at",
            "0",
            "--value",
            str(value),
            "--mocks",
            str(mocks),
            "--db",
            db,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "quarantined" in result.output
    store = RunStore(db)
    child = store.load(store.list_runs()[0].id)
    # Run ordering is timestamp-based; select the counterfactual explicitly.
    for row in store.list_runs():
        candidate = store.load(row.id)
        if candidate.metadata.get("counterfactual"):
            child = candidate
    store.close()
    assert child.final_output == "420\n"
    assert verify_script(child, script, 3).passed
    result = runner.invoke(app, ["show", rid, "--at", "0", "--db", db])
    assert result.exit_code == 0
    state = json.loads(result.output)
    assert state["boundary"]["chain_hash"] == cassette.boundaries[0].chain_hash
    assert state["replayed_events"] == 0
    bad = runner.invoke(app, ["fork", rid, "--at", "0", "--db", db])
    assert bad.exit_code != 0


def test_gemini_capture_offline_roundtrip() -> None:
    import httpx

    from flightrecorder.example_agent import make_example_run
    from flightrecorder.replay import record, verify

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["authorization"] == "Bearer test-credential"
        return httpx.Response(200, json={"choices": [{"message": {"content": "3"}}]})

    parent = record(
        make_example_run(GEMINI, api_key="test-credential"),
        httpx.MockTransport(handler),
        provider=GEMINI.name,
        model=GEMINI.default_model,
    )
    assert verify(parent, make_example_run(GEMINI), 3).passed
    assert len(calls) == 3
    assert "test-credential" not in str(parent)


def test_async_langgraph_forks_and_exports(tmp_path: Path) -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "examples/month3_langgraph.py"
    spec = importlib.util.spec_from_file_location("month3_example", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = asyncio.run(module.scenario(GEMINI, tmp_path, False))
    assert report["mutating_fork_calls"] == 0
    assert report["offline_replays"] == 6
    assert len(list(tmp_path.iterdir())) == 8


def test_tui_scrubs_without_future_state() -> None:
    from flightrecorder.tui import TimelineApp

    session = Session("record")
    for value in range(4):
        session.mediate("state", "agent", {"step": value}, partial(dict, step=value))
    cassette = Cassette(session.boundaries, session.chain, "finished")

    async def scenario() -> None:
        app = TimelineApp(cassette)
        async with app.run_test() as pilot:
            assert app.index.at(app.position)["agent_snapshot"] == {"step": 0}
            await pilot.press("right", "right", "left")
            assert app.position == 1
            assert app.index.at(app.position)["final_output"] is None
            assert state_at(cassette, app.position)["agent_snapshot"] == {"step": 1}
            await pilot.press("left", "left")
            assert app.position == 0

    asyncio.run(scenario())


def test_fork_export_preserves_quarantine() -> None:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    from flightrecorder.interop import otlp, otlp_protobuf, perfetto

    session = Session("record")
    session.mediate("tool", "quote", None, lambda: 720)
    cassette = Cassette(
        session.boundaries,
        session.chain,
        metadata={"counterfactual": True, "fork_at": 0, "parent_fingerprint": "abc"},
    )
    args = perfetto(cassette)["traceEvents"][0]["args"]
    assert args["counterfactual"] and args["parent_fingerprint"] == "abc"
    attributes = otlp(cassette)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    assert {row["key"]: row["value"] for row in attributes}["rewind.counterfactual"] == {
        "stringValue": "true"
    }
    message = ExportTraceServiceRequest.FromString(otlp_protobuf(cassette))
    assert message.resource_spans[0].scope_spans[0].spans[0].name == "quote"


def test_forks_reject_nonreplayable_and_concurrent_evidence() -> None:
    from flightrecorder.fork import ForkSession

    for metadata, match in (
        ({"concurrent": True}, "concurrent"),
        ({"replayable": False}, "trace-only"),
    ):
        with pytest.raises(ValueError, match=match):
            ForkSession(Cassette(metadata=metadata), 0, 1, {})
