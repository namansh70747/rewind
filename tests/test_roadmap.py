"""Roadmap integration contracts. Fixtures are local, never claimed as live fleet data."""

from __future__ import annotations

import asyncio
import copy
import json
import random
import time
import uuid
from functools import partial
from typing import TYPE_CHECKING, Any, TypedDict

import httpx
import pytest

from flightrecorder import Cassette, Divergence, RunStore, Session, capture, verify_run
from flightrecorder.concurrency import ConcurrentSession
from flightrecorder.demo import record_demo, recover_demo
from flightrecorder.diagnosis import diagnose, hash_bisect
from flightrecorder.fleet import fleet_map, train_classifier
from flightrecorder.integrations.langgraph import run_graph
from flightrecorder.integrations.mcp import MCPRecorder
from flightrecorder.integrity import validate
from flightrecorder.interop import ingest_otlp, otlp, perfetto
from flightrecorder.offline import offline_guard
from flightrecorder.portable import export_run, import_run
from flightrecorder.query import query
from flightrecorder.snapshots import SnapshotIndex
from flightrecorder.tools import RecordedToolError, tool

if TYPE_CHECKING:
    from pathlib import Path


def test_legacy_b2_recording_compatibility(tmp_path: Path) -> None:
    seed = Cassette(chain_algorithm="blake2b")
    session = Session("record", seed)
    session.mediate("tool", "x", None, lambda: 1)
    cassette = Cassette(session.boundaries, session.chain, chain_algorithm="blake2b")
    path = tmp_path / "legacy.json"
    export_run(cassette, path)
    assert import_run(path) == cassette
    store = RunStore(tmp_path / "legacy.db")
    try:
        assert store.load(store.save(cassette)) == cassette
    finally:
        store.close()


def test_blake3_zstd_dedup_and_gc(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "new.db")
    try:
        rid = store.save(record_demo())
        assert store.load(rid).chain_algorithm == "blake3"
        assert all(row[0].startswith("b3:") for row in store.conn.execute("SELECT hash FROM blob"))
        count = store.blob_count()
        store.save(store.load(rid))
        assert store.blob_count() == count
        store._put_blob({"orphan": True})
        assert store.garbage_collect() == 1
        assert store.blob_count() == count
    finally:
        store.close()


def test_opt_in_global_sources() -> None:
    values = []

    def agent() -> None:
        values.append([time.time(), str(uuid.uuid4()), random.random(), random.randint(1, 999)])

    with capture(sources=True) as cap:
        agent()
    assert cap.cassette
    assert verify_run(cap.cassette, agent, n=5).passed
    assert all(value == values[0] for value in values)


def test_decorated_error_replays_without_producer() -> None:
    calls = []

    @tool(name="unstable", mutating=False)
    def unstable() -> None:
        calls.append(1)
        raise ValueError("temporary outage")

    def agent() -> None:
        with pytest.raises(RecordedToolError, match="temporary outage"):
            unstable()

    with capture() as cap:
        agent()
    assert cap.cassette
    assert verify_run(cap.cassette, agent, n=3).passed
    assert len(calls) == 1


def test_http_transport_failure_retry_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def serve(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("temporary", request=request)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", serve)

    def agent() -> None:
        with httpx.Client(trust_env=False) as client:
            with pytest.raises(httpx.ReadTimeout):
                client.get("https://local.invalid/task")
            assert client.get("https://local.invalid/task").json()["ok"]

    with capture() as cap:
        agent()
    assert cap.cassette
    assert verify_run(cap.cassette, agent, n=3).passed
    assert len(calls) == 2


def test_concurrent_completion_order_and_no_reexecution() -> None:
    async def scenario() -> None:
        completion = []

        async def run(session: ConcurrentSession) -> list[Any]:
            async def call(label: str, delay: float) -> Any:
                async def producer() -> Any:
                    await asyncio.sleep(delay)
                    completion.append(label)
                    return label

                result = await session.mediate_async("tool", label, None, producer)
                observed.append(result)
                return result

            return list(await asyncio.gather(call("slow", 0.01), call("fast", 0)))

        observed: list[str] = []
        session = ConcurrentSession("record")
        assert await run(session) == ["slow", "fast"]
        assert observed == ["fast", "slow"]
        c = Cassette(session.boundaries, session.chain, metadata={"concurrent": True})
        validate(c)
        observed.clear()
        replay = ConcurrentSession("replay", c)
        with offline_guard():
            assert await run(replay) == ["slow", "fast"]
        replay.assert_fully_consumed()
        assert observed == ["fast", "slow"]
        assert completion == ["fast", "slow"]

    asyncio.run(scenario())


def test_concurrent_async_http_capture() -> None:
    counter = []

    async def agent() -> None:
        async def serve(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.001 if request.url.path == "/a" else 0)
            counter.append(1)
            return httpx.Response(200, json={"path": request.url.path})

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            results = await asyncio.gather(
                client.get("https://local.invalid/a"), client.get("https://local.invalid/b")
            )
            assert [r.json()["path"] for r in results] == ["/a", "/b"]

    with capture(concurrent=True) as cap:
        asyncio.run(agent())
    assert cap.cassette
    assert verify_run(cap.cassette, lambda: asyncio.run(agent()), n=3).passed
    assert len(counter) == 2


def test_snapshot_queries_are_bounded_and_isolated() -> None:
    s = Session("record")
    for i in range(1000):
        s.mediate("state", "agent", {"step": i}, partial(dict, step=i))
    idx = SnapshotIndex(Cassette(s.boundaries, s.chain))
    for at in (0, 14, 301, 999):
        result = idx.at(at)
        assert result["agent_snapshot"]["step"] == at
        assert result["replayed_events"] < idx.interval
        result["agent_snapshot"]["step"] = -1
        assert idx.at(at)["agent_snapshot"]["step"] == at


def test_hash_bisect_and_insertion_alignment() -> None:
    a = record_demo()
    b = recover_demo(a)
    assert hash_bisect(a, b) == 3
    s = Session("record")
    for boundary in a.boundaries:
        if boundary.seq == 2:
            s.mediate("tool", "extra", None, lambda: "inserted")
        s.mediate(
            boundary.kind,
            boundary.key,
            boundary.request,
            partial(lambda value: value, boundary.response),
        )
    longer = Cassette(s.boundaries, s.chain, a.final_output)
    report = diagnose(a, longer)
    assert report["first_difference"]["label"] == "step-inserted"
    assert sum(r["label"] != "identical" for r in report["alignment"]) == 1


def test_trace_exports_and_nonreplayable_ingest() -> None:
    c = record_demo()
    assert len(perfetto(c)["traceEvents"]) == 7
    data = otlp(c)
    spans = data["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert all(len(s["traceId"]) == 32 and len(s["spanId"]) == 16 for s in spans)
    imported = ingest_otlp(data)
    validate(imported)
    assert not verify_run(imported, lambda: None, n=1).passed


def test_query_dsl_rejects_code_and_filters() -> None:
    c = record_demo()
    assert len(query(c, 'kind == "tool"')) == 2
    assert query(c, "first response.price > 500")[0]["seq"] == 3
    with pytest.raises(ValueError):
        query(c, "__import__('os').system('x')")


def test_two_mcp_servers_replay_without_transport() -> None:
    async def run(session: ConcurrentSession, live: bool) -> list[Any]:
        async def exchange(frame: dict[str, Any]) -> dict[str, Any]:
            assert live
            return {
                "jsonrpc": "2.0",
                "id": frame["id"],
                "result": {"content": [{"type": "text", "text": frame["params"]["name"]}]},
            }

        a = MCPRecorder(session, "weather", exchange if live else None)
        b = MCPRecorder(session, "travel", exchange if live else None)
        return list(await asyncio.gather(a.call_tool("forecast", {}), b.call_tool("quote", {})))

    s = ConcurrentSession("record")
    original = asyncio.run(run(s, True))
    c = Cassette(s.boundaries, s.chain)
    replay = ConcurrentSession("replay", c)
    assert asyncio.run(run(replay, False)) == original
    replay.assert_fully_consumed()


def test_openai_sdk_record_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    openai = pytest.importorskip("openai")
    calls = []

    def serve(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "42"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", serve)

    def agent() -> None:
        with openai.OpenAI(api_key="fixture-only", max_retries=0) as client:
            assert (
                client.chat.completions.create(
                    model="test", messages=[{"role": "user", "content": "answer"}]
                )
                .choices[0]
                .message.content
                == "42"
            )

    with capture() as cap:
        agent()
    assert cap.cassette and verify_run(cap.cassette, agent, n=3).passed
    assert len(calls) == 1


def test_anthropic_sdk_record_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    anthropic = pytest.importorskip("anthropic")
    calls = []

    def serve(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "42"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", serve)

    def agent() -> None:
        with anthropic.Anthropic(api_key="fixture-only", max_retries=0) as client:
            assert (
                client.messages.create(
                    model="test", max_tokens=20, messages=[{"role": "user", "content": "answer"}]
                )
                .content[0]
                .text
                == "42"
            )

    with capture() as cap:
        agent()
    assert cap.cassette and verify_run(cap.cassette, agent, n=3).passed
    assert len(calls) == 1


def test_real_langgraph_engine_replay_and_fork() -> None:
    graph_module = pytest.importorskip("langgraph.graph")
    from flightrecorder.fork import fork_run
    from flightrecorder.replay import verify

    class State(TypedDict):
        price: int

    @tool(name="price", mutating=False)
    def price() -> int:
        return 720

    def node(state: State) -> State:
        return {"price": price()}

    graph = graph_module.StateGraph(State)
    graph.add_node("quote", node)
    graph.set_entry_point("quote")
    graph.set_finish_point("quote")
    compiled = graph.compile()

    def run(s: Session, inner: httpx.BaseTransport | None) -> str:
        return run_graph(compiled, {"price": 0}, s)

    session = Session("record")
    output = run(session, None)
    c = Cassette(session.boundaries, session.chain, output)
    assert verify(c, run, 3).passed
    index = next(b.seq for b in c.boundaries if b.kind == "tool")
    child = fork_run(
        c,
        run,
        at=index,
        value={"ok": True, "value": 420},
        mocks={("state", "langgraph/1"): lambda request: request},
    )
    assert json.loads(child.final_output)["price"] == 420
    assert verify(child, run, 3).passed


def test_fleet_clusters_are_executable_not_claimed_validated() -> None:
    pytest.importorskip("sklearn")
    runs = {str(i): record_demo(400 if i < 5 else 900) for i in range(10)}
    report = fleet_map(runs)
    assert len(report["points"]) == 10
    assert report["human_evaluation"] == "not performed"


def test_classifier_has_group_disjoint_splits() -> None:
    pytest.importorskip("sklearn")
    samples = [
        {"text": f"{label} scenario-{i} code-{i % 3}", "label": label, "group": f"{label}-{i}"}
        for label in ("timeout", "budget")
        for i in range(30)
    ]
    report = train_classifier(samples)
    groups = report["split_groups"]
    assert not set(groups["train"]) & set(groups["test"])
    assert not set(groups["validation"]) & set(groups["test"])
    assert "NOT MEASURED" in report["prompted_llm_baseline"]


def test_caught_network_attempt_does_not_silently_verify() -> None:
    import socket

    from flightrecorder import verify
    from flightrecorder.offline import NetworkBlocked

    def agent(session: Session, transport: httpx.BaseTransport | None) -> str:
        try:
            with socket.socket() as sock:
                sock.connect(("127.0.0.1", 9))
        except NetworkBlocked:
            pass
        return ""

    assert not verify(Cassette(), agent, 1).passed


def test_policy_requires_explicit_opt_in_even_for_read_only() -> None:
    from flightrecorder.policy import SideEffectPolicy, fork_with_policy

    calls = []

    def agent(session: Session, transport: httpx.BaseTransport | None) -> str:
        quote = session.mediate("tool", "quote", None, lambda: 1)
        return str(session.mediate("tool", "charge", quote, lambda: calls.append(quote)))

    session = Session("record")
    output = agent(session, None)
    parent = Cassette(session.boundaries, session.chain, output)
    calls.clear()
    with pytest.raises(Divergence):
        fork_with_policy(parent, agent, at=0, value=2, mocks={}, policy=SideEffectPolicy())
    assert not calls
    child = fork_with_policy(
        parent,
        agent,
        at=0,
        value=2,
        mocks={},
        policy=SideEffectPolicy(live_allowlist=frozenset({("tool", "charge")})),
    )
    assert calls == [2]
    assert child.metadata["counterfactual"]
    validate(child)


def test_textual_terminal_scrubber() -> None:
    pytest.importorskip("textual")
    from flightrecorder.tui import TimelineApp

    async def interact() -> None:
        app = TimelineApp(record_demo())
        async with app.run_test() as pilot:
            assert app.position == 0
            await pilot.press("right")
            assert app.position == 1
            await pilot.press("left")
            assert app.position == 0

    asyncio.run(interact())


def test_otlp_matches_official_protobuf_schema() -> None:
    import base64

    pytest.importorskip("opentelemetry.proto")
    from google.protobuf.json_format import ParseDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    data = otlp(record_demo())
    # Protobuf's generic JSON parser expects base64; OTLP/HTTP JSON specifies hex IDs.
    normalized = copy.deepcopy(data)
    for span in normalized["resourceSpans"][0]["scopeSpans"][0]["spans"]:
        for key in ("traceId", "spanId"):
            span[key] = base64.b64encode(bytes.fromhex(span[key])).decode()
    message = ParseDict(normalized, ExportTraceServiceRequest())
    assert len(message.resource_spans[0].scope_spans[0].spans) == 7


def test_persisted_snapshots_survive_gc(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "snapshots.db")
    try:
        rid = store.save(record_demo())
        assert store.index_snapshots(rid, 2) == 4
        expected = store.snapshot_at(rid, 5)
        assert expected["agent_snapshot"]["quoted_price"] == 720
        store.garbage_collect()
        assert store.snapshot_at(rid, 5) == expected
    finally:
        store.close()


def test_concurrent_decorated_tools_survive_json_storage(tmp_path: Path) -> None:
    @tool(name="square", mutating=False)
    async def square(value: int) -> int:
        await asyncio.sleep(0)
        return value * value

    async def agent() -> None:
        assert list(await asyncio.gather(square(2), square(3))) == [4, 9]

    with capture(concurrent=True) as cap:
        asyncio.run(agent())
    assert cap.cassette
    store = RunStore(tmp_path / "concurrent.db")
    try:
        restored = store.load(store.save(cap.cassette))
    finally:
        store.close()
    assert verify_run(restored, lambda: asyncio.run(agent()), n=3).passed


def test_twenty_named_seed_secrets_do_not_reach_storage(tmp_path: Path) -> None:
    from flightrecorder.redaction import redact, redact_text

    seeds = [f"unique-secret-{i}-private" for i in range(20)]
    rows = [{"password": seed, "url": f"https://example.invalid/?api_key={seed}"} for seed in seeds]
    safe = redact(rows)
    serialized = json.dumps(safe)
    assert all(seed not in serialized for seed in seeds)
    s = Session("record")
    s.mediate("test", "redaction-seeds", None, lambda: safe)
    store = RunStore(tmp_path / "secrets.db")
    try:
        loaded = store.load(store.save(Cassette(s.boundaries, s.chain)))
        assert all(seed not in json.dumps(loaded.boundaries[0].response) for seed in seeds)
    finally:
        store.close()
    assert redact_text(redact_text('"password":"tiny"')) == redact_text('"password":"tiny"')
