"""Redaction-on-write: secrets/PII must never reach the boundary log or the store.

Verifies the pattern set directly, and end-to-end that a secret embedded in an LLM
response is scrubbed before storage while replay stays bit-exact on the redacted run.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from flightrecorder import RunStore, record, verify
from flightrecorder.example_agent import make_example_run
from flightrecorder.providers import OPENAI
from flightrecorder.redaction import redact, redact_text

if TYPE_CHECKING:
    from pathlib import Path

FAKE_KEY = "sk-ant-" + "A" * 40


def test_redact_text_patterns() -> None:
    assert redact_text(FAKE_KEY) == "<redacted:anthropic-key>"
    assert redact_text("nvapi-" + "B" * 40) == "<redacted:nvidia-key>"
    assert "<redacted:email>" in redact_text("ping foo.bar@example.com please")
    assert redact_text("just a normal sentence") == "just a normal sentence"


def test_redact_walks_nested_structures() -> None:
    out = redact({"a": [FAKE_KEY, "ok"], "b": {"c": "nvapi-" + "C" * 40}, "n": 7})
    assert out == {
        "a": ["<redacted:anthropic-key>", "ok"],
        "b": {"c": "<redacted:nvidia-key>"},
        "n": 7,
    }


def _mock_leaking_secret() -> httpx.MockTransport:
    responses = [f"The number is 7 (leaked {FAKE_KEY})", "OK", "done"]
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        content = responses[i] if i < len(responses) else "x"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def test_secret_is_redacted_before_storage(tmp_path: Path) -> None:
    run = make_example_run(OPENAI, api_key="test-key")
    cassette = record(run, _mock_leaking_secret(), provider="openai", model="gpt-4o-mini")

    store = RunStore(tmp_path / "runs.db")
    run_id = store.save(cassette)
    loaded = store.load(run_id)

    dumped = json.dumps([b.response for b in loaded.boundaries])
    assert FAKE_KEY not in dumped  # the raw secret never made it into the recording
    assert "<redacted:anthropic-key>" in dumped

    # Replay is still bit-exact on the (redacted) recording.
    result = verify(loaded, run, n=10)
    assert result.passed, result.detail
    store.close()
