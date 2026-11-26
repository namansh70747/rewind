"""M2.1 — an unmodified agent records & replays bit-exact across BOTH OpenAI and Anthropic.

Capture is at the httpx transport (ADR-0007), so the only per-vendor difference is request
shaping and response parsing (`providers.py`): OpenAI uses `Bearer` auth + `choices[].message`,
Anthropic uses `x-api-key` + `content[].text`. We drive the bundled example agent against a
mock transport speaking each dialect and prove replay is byte-identical for both — no vendor
lock-in in the record/replay core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from flightrecorder import RunStore, verify
from flightrecorder.example_agent import make_example_run
from flightrecorder.providers import ANTHROPIC, OPENAI
from flightrecorder.replay import record

if TYPE_CHECKING:
    from pathlib import Path

    from flightrecorder.providers import Provider

_REPLIES = ["7", "OK", "the number 7 doubled is 14"]


def _openai_mock() -> httpx.MockTransport:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")  # OpenAI dialect
        i = state["n"]
        state["n"] += 1
        text = _REPLIES[i] if i < len(_REPLIES) else f"x{i}"
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    return httpx.MockTransport(handler)


def _anthropic_mock() -> httpx.MockTransport:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"]  # Anthropic dialect (not Bearer)
        i = state["n"]
        state["n"] += 1
        text = _REPLIES[i] if i < len(_REPLIES) else f"x{i}"
        return httpx.Response(200, json={"content": [{"text": text}]})

    return httpx.MockTransport(handler)


def _record_then_verify(provider: Provider, mock: httpx.MockTransport, tmp_path: Path) -> None:
    run = make_example_run(provider, None, api_key="record-key")
    cassette = record(run, mock, provider=provider.name, model=provider.default_model)

    store = RunStore(tmp_path / f"{provider.name}.db")
    loaded = store.load(store.save(cassette))
    store.close()

    # Replay with a fresh agent and no real key — the mock is never touched again.
    replay_agent = make_example_run(provider, None, api_key="replay-needs-no-key")
    result = verify(loaded, replay_agent, n=25)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1


def test_openai_agent_records_and_replays_bit_exact(tmp_path: Path) -> None:
    _record_then_verify(OPENAI, _openai_mock(), tmp_path)


def test_anthropic_agent_records_and_replays_bit_exact(tmp_path: Path) -> None:
    _record_then_verify(ANTHROPIC, _anthropic_mock(), tmp_path)
