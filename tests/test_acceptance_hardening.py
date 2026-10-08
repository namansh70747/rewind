"""Prevent invented explanations and false-positive corpus acceptance."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from examples.provider_corpus import agent_source

from flightrecorder.boundary import canon
from flightrecorder.demo import record_demo
from flightrecorder.evaluation import evaluate_manifest
from flightrecorder.portable import export_run
from flightrecorder.scripts import record_script
from flightrecorder.summaries import summarize_clusters

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "answer",
    [
        {"selected_feature_ids": ["UNKNOWN"]},
        {"selected_feature_ids": ["F0", "F0"]},
        {"selected_feature_ids": ["F0"], "summary": "Invented maintenance"},
        {"selected_feature_ids": []},
        {"selected_feature_ids": [None]},
    ],
)
def test_narrator_rejects_unsupported_model_claims(answer: dict[str, Any]) -> None:
    result = summarize_clusters(
        {"points": [{"id": "a", "cluster": 0}]},
        {"a": record_demo()},
        "controlled-test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"response": json.dumps(answer)})
        ),
    )
    summary = result["summaries"]["0"]
    assert summary["status"] == "unavailable"
    assert "summary" not in summary
    assert "Invented maintenance" not in json.dumps(result)


def test_fixture_integrity_failure_does_not_skip_later_results(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text("print('deterministic output')\n")
    recording = record_script(script)
    export_run(recording, tmp_path / "good.json")
    damaged = json.loads((tmp_path / "good.json").read_text())
    damaged["run"]["fingerprint"] = "bad-chain"
    damaged["checksum"] = hashlib.sha256(canon(damaged["run"])).hexdigest()
    (tmp_path / "bad.json").write_text(json.dumps(damaged))
    manifest = tmp_path / "fixtures.json"
    manifest.write_text(
        json.dumps(
            [
                {"recording": "bad.json", "script": "agent.py"},
                {"recording": "good.json", "script": "agent.py"},
            ]
        )
    )
    result = evaluate_manifest(manifest, 3)
    assert not result["passed"]
    assert [row["passed"] for row in result["fixtures"]] == [False, True]
    assert result["fixtures"][1]["replays_completed"] == 3


def test_manifest_validation_rejects_duplicates_and_path_escape(tmp_path: Path) -> None:
    manifest = tmp_path / "fixtures.json"
    row = {"recording": "good.json", "script": "agent.py"}
    for rows, message in [
        ([row, row], "duplicate"),
        ([row, 7], "each fixture"),
        ([{"recording": "../outside.json", "script": "agent.py"}], "inside"),
    ]:
        manifest.write_text(json.dumps(rows))
        with pytest.raises(ValueError, match=message):
            evaluate_manifest(manifest)


def test_fixture_runtime_exception_is_an_explicit_failure(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text("print('ok')\n")
    cassette = record_script(script)
    script.write_text("raise KeyError('broken agent')\n")
    # Match the digest to exercise execution failure, not the separate drift gate.
    cassette.metadata["source_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    export_run(cassette, tmp_path / "run.json")
    manifest = tmp_path / "fixtures.json"
    manifest.write_text(json.dumps([{"recording": "run.json", "script": "agent.py"}]))
    result = evaluate_manifest(manifest)
    assert result["passed"] is False
    assert "broken agent" in result["fixtures"][0]["detail"]


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_live_corpus_agent_records_five_steps_and_replays_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    from flightrecorder.scripts import verify_script

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-only")
    calls = []

    def serve(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if provider == "openai":
            body = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
            }
        else:
            body = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return httpx.Response(200, json=body)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", serve)
    script = tmp_path / "agent.py"
    script.write_text(agent_source(provider, "test", 1))
    cassette = record_script(script)
    assert len(cassette.boundaries) == 5
    assert verify_script(cassette, script, 3).passed
    assert len(calls) == 3, "Replay must not make additional provider calls"
