"""Offline proof for Spike A — runs in CI with no API key.

A mock HTTP transport stands in for the LLM provider (and deliberately behaves as if
the provider were nondeterministic). We record one run against it, then show that:

1. replay is bit-exact 50x (the core go/no-go, exercised deterministically);
2. the divergence oracle fails LOUD and localized when a recording is tampered;
3. a truncated recording underflows (the network kill-switch — no outbound call);
4. an input change (uncaptured nondeterminism / code drift) is caught.

The *live* go/no-go against the real provider is run separately via
``python -m spikes.spike_a record`` (see spikes/spike_a/README.md).
"""

from __future__ import annotations

import httpx
from spikes.spike_a.agent import make_run, record, verify
from spikes.spike_a.engine import Cassette

RESPONSES = ["The number is 7.", "OK", "Confirmed doubled=14."]


def _mock_transport() -> httpx.MockTransport:
    """Pretend to be a nondeterministic provider: different content per call."""
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        content = RESPONSES[i] if i < len(RESPONSES) else f"extra-{i}"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def _copy(cassette: Cassette) -> Cassette:
    return Cassette.from_json(cassette.to_json())


def test_playback_is_bit_exact_50x() -> None:
    run = make_run(api_key="test-key")
    cassette = record(run, _mock_transport())

    # uuid + clock + rng + 3 LLM calls
    assert len(cassette.boundaries) == 6
    kinds = [b.kind for b in cassette.boundaries]
    assert kinds == ["uuid", "clock", "rng", "http", "http", "http"]

    result = verify(cassette, run, n=50)
    assert result.passed, result.detail
    assert result.unique_outputs == 1
    assert result.unique_fingerprints == 1


def test_oracle_catches_tampered_recording() -> None:
    run = make_run(api_key="test-key")
    tampered = _copy(record(run, _mock_transport()))
    tampered.boundaries[3].response["body"]["choices"][0]["message"]["content"] = "TAMPERED"

    result = verify(tampered, run, n=1)
    assert not result.passed
    assert "boundary #3" in result.detail
    assert "hash-chain" in result.detail


def test_kill_switch_underflow_on_truncated_recording() -> None:
    run = make_run(api_key="test-key")
    truncated = _copy(record(run, _mock_transport()))
    truncated.boundaries = truncated.boundaries[:5]  # drop the final LLM boundary

    result = verify(truncated, run, n=1)
    assert not result.passed
    assert "underflow" in result.detail  # no network call escaped — kill-switch held


def test_input_divergence_is_caught() -> None:
    run = make_run(api_key="test-key")
    mutated = _copy(record(run, _mock_transport()))
    mutated.boundaries[3].request["body"]["messages"][0]["content"] = "A DIFFERENT PROMPT"

    result = verify(mutated, run, n=1)
    assert not result.passed
    assert "input diverged" in result.detail


def test_replay_makes_no_network_calls() -> None:
    run = make_run(api_key="test-key")
    cassette = record(run, _mock_transport())

    # A replay session is built with inner=None; nothing can reach the network.
    # A clean 50x verify proves the kill-switch holds.
    result = verify(cassette, run, n=50)
    assert result.passed

    # And an empty recording must fail loud (underflow), never silently pass.
    empty = verify(Cassette(), run, n=1)
    assert not empty.passed
    assert "underflow" in empty.detail
