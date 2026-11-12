"""Month 4 gates: hash/semantic alignment, named evidence, fleet wire fidelity."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from flightrecorder.boundary import Cassette, Divergence, Session
from flightrecorder.cli import app
from flightrecorder.diagnosis import align, diagnose
from flightrecorder.integrations.fleet import MCPServer, open_fleet
from flightrecorder.offline import offline_guard
from flightrecorder.replay import record, verify
from flightrecorder.semantic import embed_pair, load_vectors
from flightrecorder.store import RunStore


def cassette(events: list[tuple[str, str, Any, Any]], output: str = "done") -> Cassette:
    session = Session("record")
    for kind, key, request, response in events:
        session.mediate(kind, key, request, partial(lambda value: value, response))
    return Cassette(session.boundaries, session.chain, output)


def test_validated_hash_search_and_corruption() -> None:
    base = [("tool", f"tool-{i}", {"i": i}, i) for i in range(257)]
    left = cassette(base)
    for at in (0, 1, 128, 256):
        changed = copy.deepcopy(base)
        changed[at] = ("tool", f"tool-{at}", {"i": at}, -1)
        report = diagnose(left, cassette(changed))
        assert report["comparison_method"] == "hash-chain"
        assert report["hash_search"]["first_boundary"] == at
        assert report["primary_difference"]["a"] == at
        assert report["hash_search"]["comparisons"] <= math.ceil(math.log2(258))
    corrupt = copy.deepcopy(left)
    corrupt.boundaries[5].response = "tampered"
    with pytest.raises(Divergence):
        diagnose(left, corrupt)


def test_alignment_preserves_prefix_and_named_tool_choice() -> None:
    events = [("tool", "search", {"q": "GPU"}, [1]), ("tool", "finish", {}, "ok")]
    left, right = cassette(events), cassette([events[0], ("tool", "extra", {}, "yes"), events[1]])
    report = diagnose(left, right)
    assert report["comparison_method"] == "sequence-alignment"
    assert (report["primary_difference"]["a"], report["primary_difference"]["b"]) == (None, 1)
    inverse = diagnose(right, left)
    assert inverse["primary_difference"]["label"] == "step-removed"
    choice = diagnose(cassette([events[0]]), cassette([("tool", "browse", {"q": "GPU"}, [1])]))
    assert choice["primary_difference"]["category"] == "tool-choice"
    repeated = diagnose(left, cassette([events[0], events[0], events[1]]))
    assert repeated["primary_difference"]["category"] == "loop"
    assert repeated["primary_difference"]["b"] == 1


@pytest.mark.parametrize(
    "key,inputs,baseline,candidate,category",
    [
        ("reserve", {"price": 420}, "ok", "failed", "tool-result-drift"),
        ("search", {"q": "GPU"}, ["doc-a"], ["doc-b"], "retrieval-drift"),
        ("model", {}, {"finish_reason": "stop"}, {"finish_reason": "length"}, "truncation"),
        ("model", {}, {"cost": 1}, {"cost": 3}, "cost-blowup"),
    ],
)
def test_taxonomy_uses_observed_evidence(
    key: str, inputs: Any, baseline: Any, candidate: Any, category: str
) -> None:
    report = diagnose(
        cassette([("tool", key, inputs, baseline)]), cassette([("tool", key, inputs, candidate)])
    )
    assert report["primary_difference"]["category"] == category
    assert report["primary_difference"]["raw_diff"]


def test_source_noise_is_separate_from_first_decision_and_upstream_inputs() -> None:
    left = cassette([("uuid", "uuid4", None, "a"), ("tool", "charge", {"n": 1}, "ok")])
    right = cassette([("uuid", "uuid4", None, "b"), ("tool", "charge", {"n": 2}, "ok")])
    report = diagnose(left, right)
    assert report["first_difference"]["a"] == 0
    assert report["first_diverging_decision"]["a"] == 1
    assert report["primary_difference"]["input_relation"] == "different-input-or-gap"
    assert report["primary_difference"]["category"] == "arg-hallucination"
    assert "not proof" in report["primary_difference"]["summary"]
    assert report["upstream_context"]["a"] == 0


def test_provider_metadata_does_not_invent_sampling_difference() -> None:
    def response(identity: str, content: str) -> dict[str, Any]:
        return {
            "status": 200,
            "body": {
                "json": {
                    "id": identity,
                    "choices": [
                        {
                            "message": {"content": content, "role": "assistant"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            },
        }

    left = cassette([("http", "/chat/completions", {}, response("one", "yes"))])
    same = cassette([("http", "/chat/completions", {}, response("two", "yes"))])
    report = diagnose(left, same)
    assert report["first_difference"]["category"] == "metadata-only"
    assert report["first_diverging_decision"] is None
    changed = diagnose(left, cassette([("http", "/chat/completions", {}, response("two", "no"))]))
    assert changed["first_diverging_decision"]["category"] == "sampling-flake"


def test_explicit_embeddings_cached_with_source_binding_and_reverse_order() -> None:
    left = cassette([("tool", "search", {"q": "affordable GPUs"}, "a")])
    right = cassette([("tool", "search", {"q": "low cost compute"}, "b")])
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [1.0, 0.1 + i]} for i in range(len(body["input"]))
                ]
            },
        )

    cache = embed_pair(left, right, "fixture-secret", transport=httpx.MockTransport(handle))
    assert "fixture-secret" not in json.dumps(cache)
    vectors = load_vectors(cache, left, right)
    assert load_vectors(cache, right, left) == tuple(reversed(vectors))
    report = diagnose(left, right, vectors=vectors)
    assert report["comparison_method"] == "sequence-alignment"
    assert "embedding cosine" in report["alignment_method"]
    assert len(calls) == 1
    with pytest.raises(ValueError, match="does not belong"):
        load_vectors(cache, left, cassette([("tool", "search", {"q": "other"}, "b")]))
    with pytest.raises(ValueError, match="finite"):
        align(left, right, vectors=([[float("inf")]], [[1.0]]))


def test_bisect_cli_json_and_identical_exit_codes(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    left = cassette([("tool", "quote", {}, 420)])
    right = cassette([("tool", "quote", {}, 720)])
    a, b = store.save(left), store.save(right)
    store.close()
    runner = CliRunner()
    result = runner.invoke(app, ["bisect", a, b, "--json", "--db", str(tmp_path / "runs.db")])
    assert result.exit_code == 1
    assert json.loads(result.output)["primary_difference"]["category"] == "tool-result-drift"
    assert runner.invoke(app, ["bisect", a, a, "--db", str(tmp_path / "runs.db")]).exit_code == 0


def test_project_import_drift_is_detected_before_replay(tmp_path: Path) -> None:
    from flightrecorder.scripts import record_script, verify_script

    helper = tmp_path / "month4_unique_helper.py"
    helper.write_text("VALUE = 1\n")
    script = tmp_path / "agent.py"
    script.write_text("from month4_unique_helper import VALUE\nprint(VALUE)\n")
    try:
        recording = record_script(script)
        helper.write_text("VALUE = 2\n")
        with pytest.raises(
            ValueError, match=r"recorded @ SHA.*replaying @ SHA.*month4_unique_helper"
        ):
            verify_script(recording, script)
    finally:
        sys.modules.pop("month4_unique_helper", None)


def test_real_two_server_fleet_wire_frames_and_no_replay_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = Path(__file__).parent / "fixtures/mcp_server.py"
    markers = [tmp_path / f"server-{i}.txt" for i in range(2)]
    specs = [
        MCPServer(f"server-{i}", "stdio", sys.executable, [str(server), "stdio", str(marker)])
        for i, marker in enumerate(markers)
    ]

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        async def agent() -> str:
            async with open_fleet(session, specs) as fleet:
                results = await fleet.gather(
                    [
                        ("server-0", "add", {"a": 20, "b": 22}),
                        ("server-1", "add", {"a": 10, "b": 7}),
                        ("server-0", "fail", {}),
                    ]
                )
                assert results[-1]["isError"]
                return json.dumps(results, sort_keys=True)

        return asyncio.run(agent())

    recording = record(run, concurrent=True, provider="mcp-fleet", model="local-servers")
    terminal = [b.response for b in recording.boundaries if b.kind == "async-result"]
    tool_frames = [
        frame
        for outcome in terminal
        for frame in outcome.get("wire", [])
        if frame["direction"] == "request" and frame["frame"]["method"] == "tools/call"
    ]
    assert len(tool_frames) == 3
    for outcome in terminal:
        wire = outcome["wire"]
        requests = [x["frame"] for x in wire if x["direction"] == "request"]
        responses = [x["frame"] for x in wire if x["direction"] == "response"]
        assert len(requests) == len(responses) >= 1
        assert {frame["id"] for frame in requests} == {frame["id"] for frame in responses}
        assert all(frame["jsonrpc"] == "2.0" for frame in requests + responses)
    original_markers = [marker.read_text() for marker in markers]

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("offline replay attempted to start an MCP server")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    with offline_guard():
        assert verify(recording, run, 10).passed
    assert [marker.read_text() for marker in markers] == original_markers


def test_as_completed_and_incomplete_fanout_fail_without_hanging() -> None:
    from flightrecorder.concurrency import ConcurrentSession

    effects: list[str] = []

    async def run(session: ConcurrentSession) -> list[str]:
        async def call(name: str, delay: float) -> str:
            async def producer() -> str:
                effects.append(name)
                await asyncio.sleep(delay)
                return name

            return str(await session.mediate_async("tool", name, {}, producer))

        tasks = [asyncio.create_task(call("slow", 0.01)), asyncio.create_task(call("fast", 0))]
        return [await task for task in asyncio.as_completed(tasks)]

    session = ConcurrentSession("record")
    assert asyncio.run(run(session)) == ["fast", "slow"]
    recording = Cassette(session.boundaries, session.chain)
    replay = ConcurrentSession("replay", recording)
    assert asyncio.run(run(replay)) == ["fast", "slow"]
    replay.assert_fully_consumed()
    assert effects == ["slow", "fast"]

    async def incomplete() -> None:
        playback = ConcurrentSession("replay", recording, timeout=0.01)
        # Only start the slow call; replay expects the fast start before any completion.
        with pytest.raises(Divergence, match="schedule changed or incomplete"):
            await asyncio.wait_for(
                playback.mediate_async("tool", "slow", {}, lambda: asyncio.sleep(0)), 0.2
            )

    asyncio.run(incomplete())


def test_fleet_rejects_invalid_registry_before_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid registry launched a server")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)

    async def check() -> None:
        for specs in (
            [],
            [MCPServer("a", "stdio", "python"), MCPServer("a", "stdio", "python")],
            [MCPServer("a", "unknown", "python")],
        ):
            with pytest.raises(ValueError):
                async with open_fleet(Session("record"), specs):
                    pytest.fail("invalid registry was accepted")

    asyncio.run(check())


def test_reversed_comparison_recomputes_directional_taxonomy(tmp_path: Path) -> None:
    from flightrecorder.dashboard import render_dashboard

    left = cassette([("llm", "model", {}, {"cost": 1})])
    right = cassette([("llm", "model", {}, {"cost": 4})])
    path = tmp_path / "review.html"
    render_dashboard({"Cheap": left, "Expensive": right}, path)
    payload = (
        path.read_text()
        .split('<script id="recordings" type="application/json">')[1]
        .split("</script>")[0]
    )
    report = json.loads(payload)["comparisons"][0]
    assert report["diagnosis"]["primary_difference"]["category"] == "cost-blowup"
    assert report["reverse_diagnosis"]["primary_difference"]["category"] != "cost-blowup"


def test_cosine_cost_aligns_paraphrased_repeated_tool_inputs() -> None:
    left = cassette([("tool", "search", {"q": "affordable GPU"}, "a")])
    right = cassette(
        [
            ("tool", "search", {"q": "distant stars"}, "x"),
            ("tool", "search", {"q": "low cost graphics card"}, "a"),
        ]
    )
    assert align(left, right, vectors=([[1.0, 0.0]], [[0.0, 1.0], [1.0, 0.0]])) == [
        (None, 0),
        (0, 1),
    ]
    assert align(left, right, vectors=([[1.0, 0.0]], [[1.0, 0.0], [0.0, 1.0]])) == [
        (0, 0),
        (None, 1),
    ]
