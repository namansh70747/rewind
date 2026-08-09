"""Global capture of an UNMODIFIED agent — no `flightrecorder` imports in the agent.

Proves `capture()` records a plain-`httpx` agent and `verify_run()` replays it bit-exact
offline. The agent below only imports/uses `httpx` — exactly what a real, untouched agent
would look like. The provider is stubbed at `httpx.HTTPTransport.handle_request` so the
test needs no key or network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from flightrecorder import RunStore, capture, verify_run

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

RESPONSES = ["seven", "ok", "done"]
_URL = "https://api.openai.com/v1/chat/completions"


def _unmodified_agent() -> str:
    """A normal agent: plain httpx, default client, zero knowledge of flightrecorder."""
    out = []
    with httpx.Client() as client:
        for prompt in ("first", "second"):
            resp = client.post(
                _URL, json={"model": "m", "messages": [{"role": "user", "content": prompt}]}
            )
            out.append(resp.json()["choices"][0]["message"]["content"])
    return " ".join(out)


def _stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"n": 0}

    def fake_handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        content = RESPONSES[i] if i < len(RESPONSES) else f"x{i}"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}, request=request
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)


def test_capture_and_replay_unmodified_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch)
    store = RunStore(tmp_path / "runs.db")

    with capture(store, provider="openai", model="m") as cap:
        _unmodified_agent()

    assert cap.run_id is not None
    assert cap.cassette is not None
    # two HTTP boundaries captured with no changes to the agent
    assert [b.kind for b in cap.cassette.boundaries] == ["http", "http"]

    # replay 25x, bit-exact, offline (kill-switch on — the stub is never called again)
    result = verify_run(cap.cassette, _unmodified_agent, n=25)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1
    store.close()


def test_replay_diverges_loudly_if_agent_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch)
    with capture(provider="openai", model="m") as cap:
        _unmodified_agent()
    assert cap.cassette is not None

    def _changed_agent() -> str:
        # One extra call the recording never saw -> must fail loud, not silently pass.
        with httpx.Client() as client:
            for prompt in ("first", "second", "third"):
                client.post(
                    _URL, json={"model": "m", "messages": [{"role": "user", "content": prompt}]}
                )
        return "changed"

    result = verify_run(cap.cassette, _changed_agent, n=1)
    assert not result.passed
