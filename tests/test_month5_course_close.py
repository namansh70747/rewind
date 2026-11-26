"""Course close for Month 5 leftover gates (substitute fleet + keyword baseline)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from flightrecorder.cli import app
from flightrecorder.month5 import close_month5_gates


def test_course_close_beats_keyword_stub_and_matches_fresh_failure() -> None:
    pytest.importorskip("sklearn")
    report = close_month5_gates(8)
    assert report["substitute_fleet_runs"] == 24
    assert report["fresh_failure"]["likely_cause"] == "tool-error"
    assert report["heuristic_baseline"]["classifier_beats_baseline"] is True
    assert report["policy_gate_recorded"] is True
    assert report["policy_gate_changed"] is False
    assert all(item["run_id"].startswith("tool-error") for item in report["neighbors"])


def test_live_gemini_baseline_uses_allowed_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("sklearn")
    from flightrecorder.month5 import live_prompted_predictions

    monkeypatch.setenv("GEMINI_API_KEY", "fixture-only")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def serve(self, request):  # type: ignore[no-untyped-def]
        import httpx

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "this looks like a transport-timeout",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("httpx.HTTPTransport.handle_request", serve)
    inputs = {
        "labels": ["tool-error", "transport-timeout", "context-budget"],
        "inputs": [{"id": "abc", "text": "ReadTimeout on POST /v1/chat"}],
    }
    result = live_prompted_predictions(inputs)
    assert result is not None
    assert result["provenance"]["provider"] == "gemini"
    assert result["predictions"][0]["label"] == "transport-timeout"


def test_eval_cli_is_a_ci_gate() -> None:
    kept = CliRunner().invoke(app, ["eval", "--n", "1", "--budget", "500"])
    assert kept.exit_code == 0, kept.output
    assert json.loads(kept.output)["policy_gate"]["passed"] is True
