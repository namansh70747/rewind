"""Acceptance coverage for previously partial transport and graph workflows."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

import httpx
import pytest

from flightrecorder.boundary import Cassette, Session
from flightrecorder.integrations.langgraph import arun_graph
from flightrecorder.integrations.mcp_client import mcp_http, mcp_stdio
from flightrecorder.offline import offline_guard
from flightrecorder.tools import tool

SERVER = Path(__file__).parent / "fixtures" / "mcp_server.py"


@pytest.mark.parametrize("transport", ["stdio", "streamable-http"])
def test_managed_mcp_actual_server_then_replay_without_server(
    tmp_path: Path, transport: str
) -> None:
    pytest.importorskip("mcp")
    marker = tmp_path / "effects.txt"
    process = None
    port = 0
    if transport == "streamable-http":
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, str(SERVER), transport, str(marker), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline or process.poll() is not None:
                    process.terminate()
                    process.wait(timeout=5)
                    pytest.fail("local MCP HTTP server did not start")
                time.sleep(0.05)

    async def run(session: Session) -> str:
        context = (
            mcp_stdio(session, "calculator", sys.executable, [str(SERVER), transport, str(marker)])
            if transport == "stdio"
            else mcp_http(session, "calculator", f"http://127.0.0.1:{port}/mcp")
        )
        async with context as client:
            assert client.initialization["serverInfo"]["name"] == "rewind-test"
            assert {t["name"] for t in (await client.list_tools())["tools"]} == {"add", "fail"}
            result = await client.call_tool("add", {"a": 20, "b": 22})
            error = await client.call_tool("fail", {})
            assert error["isError"] is True
            return json.dumps(result, sort_keys=True)

    try:
        session = Session("record")
        output = asyncio.run(run(session))
    finally:
        if process:
            process.terminate()
            process.wait(timeout=5)
    cassette = Cassette(session.boundaries, session.chain, output)
    with offline_guard() as audit:
        for _ in range(3):
            replay = Session("replay", cassette)
            assert asyncio.run(run(replay)) == output
            replay.assert_fully_consumed()
    assert not audit.blocked_operations
    assert marker.read_text() == "called\n"
    assert len(cassette.boundaries) == 4


def test_async_langgraph_checkpointer_isolated_replay() -> None:
    graph_module = pytest.importorskip("langgraph.graph")
    from langgraph.checkpoint.memory import InMemorySaver

    class State(TypedDict):
        price: int

    calls: list[int] = []

    @tool(name="async-quote", mutating=False)
    async def quote() -> int:
        calls.append(1)
        await asyncio.sleep(0)
        return 420

    async def node(state: State) -> State:
        return {"price": await quote()}

    async def run(session: Session) -> str:
        graph = graph_module.StateGraph(State)
        graph.add_node("quote", node)
        graph.set_entry_point("quote")
        graph.set_finish_point("quote")
        compiled = graph.compile(checkpointer=InMemorySaver())
        return await arun_graph(
            compiled, {"price": 0}, session, {"configurable": {"thread_id": "isolated"}}
        )

    session = Session("record")
    output = asyncio.run(run(session))
    cassette = Cassette(session.boundaries, session.chain, output)
    with offline_guard():
        for _ in range(3):
            replay = Session("replay", cassette)
            assert asyncio.run(run(replay)) == output
            replay.assert_fully_consumed()
    assert calls == [1]
    assert json.loads(output) == {"price": 420}


def test_concurrent_errors_and_cancellations_have_replayable_terminal_events() -> None:
    from flightrecorder.concurrency import ConcurrentSession, RecordedBoundaryError

    calls: list[str] = []

    async def run(session: ConcurrentSession) -> list[str]:
        async def error() -> None:
            calls.append("error")
            await asyncio.sleep(0)
            raise ValueError("bad request")

        async def cancelled() -> None:
            calls.append("cancel")
            raise asyncio.CancelledError

        values = await asyncio.gather(
            session.mediate_async("tool", "error", {}, error),
            session.mediate_async("tool", "cancel", {}, cancelled),
            return_exceptions=True,
        )
        assert isinstance(values[0], RecordedBoundaryError)
        assert isinstance(values[1], asyncio.CancelledError)
        return [type(value).__name__ + ":" + str(value) for value in values]

    session = ConcurrentSession("record")
    output = asyncio.run(run(session))
    cassette = Cassette(session.boundaries, session.chain)
    replay = ConcurrentSession("replay", cassette)
    assert asyncio.run(run(replay)) == output
    replay.assert_fully_consumed()
    assert calls == ["error", "cancel"]
    assert {b.kind for b in cassette.boundaries} >= {"async-error", "async-cancel"}


def test_baseline_requires_exact_heldout_ids_and_measures_scores() -> None:
    from flightrecorder.fleet import compare_baseline

    report = {
        "dataset_sha256": "fixture",
        "held_out": [
            {"id": "a", "expected": "timeout", "predicted": "timeout"},
            {"id": "b", "expected": "budget", "predicted": "budget"},
        ],
    }
    baseline: dict[str, Any] = {
        "provenance": {
            "provider": "synthetic-test",
            "model": "fixture",
            "prompt_sha256": "fixture",
        },
        "predictions": [{"id": "a", "label": "timeout"}, {"id": "b", "label": "timeout"}],
    }
    result = compare_baseline(report, baseline)
    assert result["classifier_macro_f1"] == 1
    assert result["prompted_baseline_macro_f1"] == pytest.approx(1 / 3)
    assert result["classifier_beats_baseline"]
    baseline["predictions"].pop()
    with pytest.raises(ValueError, match="exactly one"):
        compare_baseline(report, baseline)


def test_script_source_and_concurrency_flags_survive_storage(tmp_path: Path) -> None:
    from flightrecorder.scripts import record_script, verify_script
    from flightrecorder.store import RunStore

    script = tmp_path / "concurrent.py"
    script.write_text("""import asyncio, random, time, uuid
from flightrecorder import tool
@tool(name='square', mutating=False)
async def square(n):
    await asyncio.sleep(0)
    return n*n
async def main():
    print(await asyncio.gather(square(2), square(3)))
print(random.random(), time.time(), uuid.uuid4())
asyncio.run(main())
""")
    cassette = record_script(script, concurrent=True, sources=True)
    store = RunStore(tmp_path / "runs.db")
    try:
        restored = store.load(store.save(cassette))
    finally:
        store.close()
    assert restored.metadata["concurrent"] and restored.metadata["sources"]
    assert verify_script(restored, script, 3).passed


def test_fork_rejects_swallowed_unmediated_network() -> None:
    from flightrecorder.fork import fork_run
    from flightrecorder.offline import NetworkBlocked

    session = Session("record")
    session.mediate("tool", "x", {}, lambda: 1)
    cassette = Cassette(session.boundaries, session.chain, "1")

    def agent(s: Session, transport: httpx.BaseTransport | None) -> str:
        value = s.mediate("tool", "x", {}, lambda: 1)
        try:
            with socket.socket() as sock:
                sock.connect(("127.0.0.1", 9))
        except NetworkBlocked:
            pass
        return str(value)

    with pytest.raises(NetworkBlocked, match="even if"):
        fork_run(cassette, agent, at=0, value=2)


def test_streamed_credentials_whitespace_and_escapes_never_enter_frames() -> None:
    from flightrecorder.interceptors.transport import _encode_response

    raw = b'data: {"password":"two words \\"quoted\\" secret","token":"short token"}\n\n'
    frames = _encode_response([raw[:27], raw[27:]], "text/event-stream")
    stored = json.dumps(frames)
    assert "two words" not in stored and "short token" not in stored
    assert "chunk_bytes_b64" not in frames
    assert "<redacted:field>" in stored


def test_safe_sse_chunk_bytes_survive_split_utf8_exactly() -> None:
    from flightrecorder.interceptors.transport import _encode_response, _rebuild_response

    raw = 'data: {"text":"हैलो"}\n\n'.encode()
    chunks = [raw[:17], raw[17:19], raw[19:]]
    encoded = _encode_response(chunks, "text/event-stream")
    response = _rebuild_response({"status": 200, **encoded}, httpx.Request("GET", "https://test/"))
    assert list(response.iter_raw()) == chunks


def test_streamed_escaped_json_keys_redact_before_base64_storage() -> None:
    from flightrecorder.interceptors.transport import _encode_response

    raw = b'data: {"pass\\u0077ord":\ndata: "hidden words"}\n\n'
    frames = _encode_response([raw[:20], raw[20:]], "text/event-stream")
    assert "hidden words" not in json.dumps(frames)
    assert "chunk_bytes_b64" not in frames


def test_policy_manifest_defaults_do_not_authorize_live_tools(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from flightrecorder.cli import app
    from flightrecorder.policy import policy_from_manifest

    path = tmp_path / "policy.json"
    result = CliRunner().invoke(app, ["policy-set", str(path), "tool", "search", "--no-mutating"])
    assert result.exit_code == 0, result.output
    data = json.loads(path.read_text())
    policy = policy_from_manifest(data)
    assert ("tool", "search") in policy.read_only
    assert not policy.permits("tool", "search")
    data["tools"][0]["live"] = "false"
    with pytest.raises(ValueError, match="booleans"):
        policy_from_manifest(data)


def test_semantic_alignment_vectors_are_validated() -> None:
    from flightrecorder.diagnosis import align

    first, second = Session("record"), Session("record")
    first.mediate("tool", "search", {"query": "cheap lodging"}, lambda: "a")
    second.mediate("tool", "search", {"query": "affordable hotels"}, lambda: "b")
    a, b = Cassette(first.boundaries, first.chain), Cassette(second.boundaries, second.chain)
    assert align(a, b, vectors=([[1.0, 0.0]], [[0.99, 0.01]])) == [(0, 0)]
    with pytest.raises(ValueError, match="finite"):
        align(a, b, vectors=([[float("nan"), 0.0]], [[1.0, 0.0]]))
    with pytest.raises(ValueError, match="count"):
        align(a, b, vectors=([], [[1.0, 0.0]]))
