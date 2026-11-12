"""Planner acceptance: checkpoint threads, completion order, deltas and experiments."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import TYPE_CHECKING, Any, TypedDict

import pytest

from flightrecorder.boundary import Cassette, Session
from flightrecorder.experiments import evaluate_forks
from flightrecorder.fork import fork_run, recorded_tool_mocks
from flightrecorder.integrations.langgraph import capture_checkpoint, run_graph
from flightrecorder.replay import verify
from flightrecorder.state import decode_state, encode_state
from flightrecorder.store import RunStore
from flightrecorder.tools import tool

if TYPE_CHECKING:
    from pathlib import Path

    import httpx


class PriceState(TypedDict):
    price: int
    receipt: str


def test_checkpoint_callback_fork_and_native_resume_comparison(tmp_path: Path) -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import StateGraph

    calls: list[str] = []

    @tool(name="gate.quote", mutating=False)
    def quote() -> int:
        calls.append("quote")
        return 720

    @tool(name="gate.reserve", mutating=True)
    def reserve(price: int) -> str:
        calls.append("reserve")
        return f"simulated-{price}"

    def make_graph() -> Any:
        graph = StateGraph(PriceState)
        graph.add_node("quote", lambda state: {"price": quote()})
        graph.add_node("finish", lambda state: {"receipt": reserve(state["price"])})
        graph.set_entry_point("quote")
        graph.add_edge("quote", "finish")
        graph.set_finish_point("finish")
        return graph.compile(checkpointer=InMemorySaver())

    recorded_graphs = []
    config = {"configurable": {"thread_id": "existing-thread"}}

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        graph = make_graph()
        recorded_graphs.append(graph)
        result = run_graph(graph, {"price": 0, "receipt": ""}, session, config, callbacks=True)
        checkpoint = capture_checkpoint(graph, config, session)
        assert checkpoint["thread_id"] == "existing-thread"
        assert checkpoint["values"] == json.loads(result)
        return result

    session = Session("record")
    result = run(session, None)
    parent = Cassette(session.boundaries, session.chain, result)
    assert any(b.kind == "callback" for b in parent.boundaries)
    assert parent.boundaries[-1].kind == "checkpoint"
    calls.clear()
    assert verify(parent, run, 3).passed
    assert not calls
    at = next(b.seq for b in parent.boundaries if b.key == "gate.quote")
    mocks = recorded_tool_mocks(parent, at=at)
    mocks.update(
        {
            (b.kind, b.key): lambda request: request
            for b in parent.boundaries
            if b.kind in {"state", "callback", "checkpoint"}
        }
    )
    child = fork_run(parent, run, at=at, value={"ok": True, "value": 420}, mocks=mocks)
    assert json.loads(child.final_output)["price"] == 420
    assert not calls
    assert verify(child, run, 3).passed
    assert not calls
    # Native checkpoint resume really re-executes the later external producer.
    graph = recorded_graphs[0]
    historical = next(s for s in graph.get_state_history(config) if s.next == ("finish",))
    graph.invoke(None, config=historical.config)
    assert calls == ["reserve"]
    (tmp_path / "native-resume-comparison.json").write_text(
        json.dumps(
            {
                "framework": "LangGraph with InMemorySaver",
                "thread_id": "existing-thread",
                "rewind_exact_replays": 6,
                "rewind_replay_producer_calls": 0,
                "safe_fork_producer_calls": 0,
                "native_checkpoint_resume_producer_calls": 1,
                "callback_boundaries": sum(b.kind == "callback" for b in parent.boundaries),
                "checkpoint_captured": True,
            },
            indent=2,
        )
    )


def test_persisted_snapshot_deltas_schema_gc_and_legacy(tmp_path: Path) -> None:
    session = Session("record")
    for step in range(100):
        session.mediate("state", "agent", {"step": step}, partial(dict, step=step))
    cassette = Cassette(session.boundaries, session.chain)
    path = tmp_path / "runs.db"
    store = RunStore(path)
    rid = store.save(cassette)
    store.index_snapshots(rid, 5)
    manifests = [
        store._get_blob(row[0])
        for row in store.conn.execute(
            "SELECT observed_hash FROM snapshot WHERE run_id = ? ORDER BY seq", (rid,)
        )
    ]
    assert manifests[1]["base"] is not None
    assert manifests[5]["base"] is None
    assert all(len(m["updates"]) == 1 for m in manifests)
    assert store.snapshot_at(rid, 99)["agent_snapshot"] == {"step": 99}
    store.garbage_collect()
    store.close()
    store = RunStore(path)
    try:
        for at in range(100):
            state = store.snapshot_at(rid, at)
            assert state["agent_snapshot"] == {"step": at}
            assert state["replayed_events"] < 5
        # Pre-envelope snapshots remain readable.
        refs = {"state:agent": store._put_blob({"step": 0})}
        with store.conn:
            store.conn.execute(
                "UPDATE snapshot SET observed_hash=?, state_hash=? WHERE run_id=? AND seq=0",
                (store._put_blob(refs), store._put_blob({"step": 0}), rid),
            )
        assert store.snapshot_at(rid, 0)["agent_snapshot"] == {"step": 0}
    finally:
        store.close()


def test_logical_state_is_versioned_and_nonexecutable() -> None:
    from langchain_core.messages import AIMessage

    payload = {"messages": [AIMessage(content="hello")], "memory": {"cursor": 2}}
    state = decode_state(encode_state(payload))
    assert state["messages"][0]["content"] == "hello"
    assert state["memory"]["cursor"] == 2
    with pytest.raises(ValueError, match="unsupported logical-state"):
        encode_state(object())
    with pytest.raises(ValueError, match="envelope"):
        decode_state({"schema": "rewind.logical-state", "version": 2, "value": {}})
    with pytest.raises(ValueError):
        encode_state(float("nan"))


class ParallelState(TypedDict):
    slow: int
    fast: int


def test_real_langgraph_async_completion_order() -> None:
    from langgraph.graph import END, START, StateGraph

    from flightrecorder.concurrency import ConcurrentSession
    from flightrecorder.integrations.langgraph import arun_graph
    from flightrecorder.offline import offline_guard

    calls = []

    @tool(name="gate.async", mutating=False)
    async def fetch(label: str, delay: float) -> int:
        calls.append(label)
        await asyncio.sleep(delay)
        return 1

    async def slow(state: ParallelState) -> dict[str, int]:
        return {"slow": await fetch("slow", 0.01)}

    async def fast(state: ParallelState) -> dict[str, int]:
        return {"fast": await fetch("fast", 0)}

    graph = StateGraph(ParallelState)
    graph.add_node("slow", slow)
    graph.add_node("fast", fast)
    graph.add_edge(START, "slow")
    graph.add_edge(START, "fast")
    graph.add_edge("slow", END)
    graph.add_edge("fast", END)
    compiled = graph.compile()

    async def scenario() -> None:
        recorded = ConcurrentSession("record")
        output = await arun_graph(compiled, {"slow": 0, "fast": 0}, recorded)
        completions = [b for b in recorded.boundaries if b.kind == "async-result"]
        assert [b.request["request"]["args"][0] for b in completions] == ["fast", "slow"]
        cassette = Cassette(
            recorded.boundaries, recorded.chain, output, metadata={"concurrent": True}
        )
        calls.clear()
        replay = ConcurrentSession("replay", cassette)
        with offline_guard():
            assert await arun_graph(compiled, {"slow": 0, "fast": 0}, replay) == output
        replay.assert_fully_consumed()
        assert replay.chain == cassette.fingerprint
        assert not calls

    asyncio.run(scenario())


def test_controlled_fork_experiments_recreate_fixtures(tmp_path: Path) -> None:
    effects = []

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        price = session.mediate("tool", "quote", None, lambda: 720)
        session.mediate("tool", "reserve", price, lambda: effects.append(price))
        return str(price)

    session = Session("record")
    parent = Cassette(final_output=run(session, None))
    parent.boundaries, parent.fingerprint = session.boundaries, session.chain
    effects.clear()
    store = RunStore(tmp_path / "experiments.db")
    report = evaluate_forks(
        parent,
        run,
        at=0,
        values=[420, 600],
        make_mocks=lambda: recorded_tool_mocks(parent, at=0),
        score=lambda output: float(int(output) <= 500),
        store=store,
    )
    assert [row["score"] for row in report["trials"]] == [1.0, 0.0]
    assert all(row["replays"] == 3 for row in report["trials"])
    assert not effects
    for row in report["trials"]:
        assert store.load(row["run_id"]).metadata["counterfactual"]
    store.close()
    (tmp_path / "fork-experiments.json").write_text(json.dumps(report, indent=2))


def test_script_cli_defaults_to_tool_simulation_and_manifest_opt_in(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from flightrecorder.cli import app
    from flightrecorder.scripts import record_script, verify_script

    marker = tmp_path / "effect.txt"
    script = tmp_path / "agent.py"
    script.write_text(f"""from pathlib import Path
from flightrecorder.tools import tool
@tool(name="gate.cli.quote", mutating=False)
def quote():
    return 720
@tool(name="gate.cli.charge", mutating=True)
def charge(price):
    Path({str(marker)!r}).write_text(str(price))
    return price
print(charge(quote()))
""")
    parent = record_script(script)
    db = tmp_path / "store.db"
    store = RunStore(db)
    rid = store.save(parent)
    store.close()
    value, mocks, policy = (
        tmp_path / "value.json",
        tmp_path / "mocks.json",
        tmp_path / "policy.json",
    )
    value.write_text('{"ok":true,"value":420}')
    mocks.write_text("{}")
    runner = CliRunner()
    args = [
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
        str(db),
    ]
    simulated = runner.invoke(app, args)
    assert simulated.exit_code == 0, simulated.output
    assert marker.read_text() == "720"
    configured = runner.invoke(
        app, ["policy-set", str(policy), "tool", "gate.cli.charge", "--live"]
    )
    assert configured.exit_code == 0, configured.output
    live = runner.invoke(app, [*args, "--policy", str(policy)])
    assert live.exit_code == 0, live.output
    assert marker.read_text() == "420"
    store = RunStore(db)
    try:
        children = [store.load(row.id) for row in store.list_runs() if row.id != rid]
        assert len(children) == 2
        for child in children:
            assert child.metadata["counterfactual"]
            assert verify_script(child, script, 3).passed
        assert marker.read_text() == "420"
    finally:
        store.close()


def test_openinference_identifies_http_model_boundaries() -> None:
    from flightrecorder.interop import otlp, perfetto

    session = Session("record")
    session.mediate("http", "/v1/chat/completions", {}, lambda: {})
    cassette = Cassette(session.boundaries, session.chain)
    span = otlp(cassette)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = {row["key"]: row["value"] for row in span["attributes"]}
    assert attributes["openinference.span.kind"] == {"stringValue": "LLM"}
    event = perfetto(cassette)["traceEvents"][0]
    assert event["ph"] == "X" and event["dur"] == 1


def test_native_checkpoint_can_restore_declared_values_before_resume() -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import StateGraph

    from flightrecorder.integrations.langgraph import restore_checkpoint

    def graph() -> Any:
        builder = StateGraph(PriceState)
        builder.add_node("quote", lambda state: {"price": 420})
        builder.add_node("finish", lambda state: {"receipt": str(state["price"])})
        builder.set_entry_point("quote")
        builder.add_edge("quote", "finish")
        builder.set_finish_point("finish")
        return builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "restore-thread"}}
    source = graph()
    source.invoke({"price": 0, "receipt": ""}, config=config, interrupt_after=["quote"])
    session = Session("record")
    evidence = capture_checkpoint(source, config, session)
    assert evidence["next"] == ["finish"]
    restored = graph()
    restored_config = restore_checkpoint(restored, evidence, config, as_node="quote")
    assert restored.invoke(None, config=restored_config)["receipt"] == "420"
    with pytest.raises(ValueError, match="frontier"):
        restore_checkpoint(graph(), evidence, config, as_node="finish")

    async def async_restore() -> None:
        from flightrecorder.integrations.langgraph import acapture_checkpoint, arestore_checkpoint

        captured = await acapture_checkpoint(source, config, Session("record"))
        target = graph()
        target_config = await arestore_checkpoint(target, captured, config, as_node="quote")
        assert (await target.ainvoke(None, config=target_config))["receipt"] == "420"

    asyncio.run(async_restore())


def test_snapshot_binding_rejects_cross_run_cache(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "bound.db")
    try:
        ids = []
        for value in (1, 2):
            session = Session("record")
            session.mediate("state", "agent", None, partial(dict, value=value))
            rid = store.save(Cassette(session.boundaries, session.chain))
            store.index_snapshots(rid)
            ids.append(rid)
        other = store.conn.execute(
            "SELECT observed_hash FROM snapshot WHERE run_id=?", (ids[1],)
        ).fetchone()[0]
        with store.conn:
            store.conn.execute(
                "UPDATE snapshot SET observed_hash=? WHERE run_id=?", (other, ids[0])
            )
        with pytest.raises(ValueError, match="does not belong"):
            store.snapshot_at(ids[0], 0)
    finally:
        store.close()
