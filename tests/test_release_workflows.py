"""Remaining roadmap release workflows: pacing, configurable redaction, narration."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx
import pytest

from flightrecorder.demo import record_demo
from flightrecorder.redaction import RedactionRules, redact, redaction_rules
from flightrecorder.streaming import chunk_deadlines, stream_playback_timing
from flightrecorder.summaries import summarize_clusters

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("asynchronous", [False, True])
def test_stream_pacing_replays_offsets_with_injected_clock(
    monkeypatch: pytest.MonkeyPatch, asynchronous: bool
) -> None:
    from flightrecorder.interceptors import transport

    waits: list[float] = []

    async def asleep(value: float) -> None:
        waits.append(value)

    monkeypatch.setattr(
        transport, "time", SimpleNamespace(monotonic=lambda: 0.0, sleep=waits.append)
    )
    monkeypatch.setattr(transport, "asyncio", SimpleNamespace(sleep=asleep))
    rec = {"status": 200, "chunks": ["a", "b"], "chunk_offsets_ns": [100_000_000, 300_000_000]}
    response = transport._rebuild_response(
        rec, httpx.Request("GET", "https://test/"), is_async=asynchronous, timing_scale=0.5
    )
    if asynchronous:

        async def consume() -> list[bytes]:
            return [chunk async for chunk in response.aiter_raw()]

        assert asyncio.run(consume()) == [b"a", b"b"]
    else:
        assert list(response.iter_raw()) == [b"a", b"b"]
    assert waits == [0.05, 0.15]
    with pytest.raises(ValueError, match="monotonic"):
        chunk_deadlines([2, 1], 2, 1)
    with pytest.raises(ValueError, match="30-second"):
        chunk_deadlines([31_000_000_000], 1, 1)
    with pytest.raises(ValueError), stream_playback_timing(float("nan")):
        pass


def test_custom_redaction_is_scoped_and_never_saved(tmp_path: Path) -> None:
    from flightrecorder.portable import export_run
    from flightrecorder.scripts import record_script, verify_script

    rules = RedactionRules.from_json(
        {"extra_keys": ["student_id"], "literals": ["private literal"]}
    )
    with redaction_rules(rules):
        assert redact({"student_id": 42, "message": "private literal"}) == {
            "student_id": "<redacted:field>",
            "message": "<redacted:custom>",
        }
        script = tmp_path / "agent.py"
        script.write_text("print('private literal')\n")
        cassette = record_script(script)
        assert verify_script(cassette, script, 2).passed
        export_run(cassette, tmp_path / "run.json")
        assert "private literal" not in (tmp_path / "run.json").read_text()
    assert redact({"student_id": 42}) == {"student_id": 42}
    with pytest.raises(ValueError):
        RedactionRules.from_json({"literals": [""]})


def test_ollama_cluster_summary_contract_and_failure_reporting() -> None:
    report = {"points": [{"id": "a", "cluster": 0}, {"id": "b", "cluster": -1}]}
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        requests.append(data)
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "selected_feature_ids": ["F0"],
                    }
                )
            },
        )

    result = summarize_clusters(
        report,
        {"a": record_demo(), "b": record_demo()},
        "test-only",
        transport=httpx.MockTransport(handler),
    )
    assert result["summaries"]["0"]["status"] == "generated"
    assert len(requests) == 1 and requests[0]["stream"] is False
    assert requests[0]["options"]["num_predict"] == 128
    assert "F0" in requests[0]["format"]["properties"]["selected_feature_ids"]["items"]["enum"]
    assert "do not establish a root cause" in result["summaries"]["0"]["summary"]
    assert result["narration"]["review_required"]
    bad = summarize_clusters(
        report,
        {"a": record_demo(), "b": record_demo()},
        "test-only",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    assert bad["summaries"]["0"]["status"] == "unavailable"
    with pytest.raises(ValueError, match="local"):
        summarize_clusters(report, {}, "model", endpoint="https://external.example")


def test_release_gate_rejects_missing_tampered_and_outside_evidence(tmp_path: Path) -> None:
    import hashlib

    from flightrecorder.release import GATES, release_check

    manifest = tmp_path / "checklist.json"
    manifest.write_text(json.dumps({"version": 1, "gates": {}}))
    assert not release_check(manifest)["checklist_complete"]
    evidence = tmp_path / "unit-fixture.txt"
    evidence.write_text("synthetic unit-test evidence, not an actual approval")
    entry = {
        "status": "passed",
        "reviewer": "unit-test only",
        "reference": "unit-test fixture",
        "artifact": evidence.name,
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    manifest.write_text(json.dumps({"version": 1, "gates": dict.fromkeys(GATES, entry)}))
    assert release_check(manifest)["checklist_complete"]
    evidence.write_text("changed")
    assert not release_check(manifest)["checklist_complete"]
    entry["artifact"] = "../outside.txt"
    manifest.write_text(json.dumps({"version": 1, "gates": dict.fromkeys(GATES, entry)}))
    assert not release_check(manifest)["checklist_complete"]


def test_custom_redaction_does_not_rewrite_its_own_placeholders() -> None:
    with redaction_rules(RedactionRules(literals=("redacted", "field"))):
        once = redact({"password": "value", "text": "redacted and field"})
        assert redact(once) == once


def test_otlp_protobuf_export_preserves_trace_ids_and_boundary_values(tmp_path: Path) -> None:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    from flightrecorder.interop import otlp, write_trace

    cassette = record_demo()
    path = tmp_path / "trace.pb"
    write_trace(cassette, path, "otlp-protobuf")
    request = ExportTraceServiceRequest.FromString(path.read_bytes())
    spans = request.resource_spans[0].scope_spans[0].spans
    assert len(spans) == 7
    assert (
        spans[0].trace_id.hex()
        == otlp(cassette)["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
    )
    assert spans[3].name == "price_lookup"
