"""M2.3 — a retry loop replays its recorded failures **in order** (the occurrence index).

An unmodified agent hits one endpoint that fails twice (503) before succeeding (200). Every
call goes to the *same* URL, so ordinal-by-position matching alone is ambiguous; the
occurrence index (algorithms-and-math §2) is what pins call #0 → #1 → #2 to the right
recorded responses. We prove the recorded failures come back in the same order on replay,
bit-exact and offline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from flightrecorder import RunStore, capture, verify_run
from flightrecorder.boundary import occurrences

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_URL = "https://api.example/v1/do"


def _retry_agent() -> str:
    """Unmodified agent: retry on a 5xx, return the result on the first 200."""
    with httpx.Client() as client:
        for _ in range(5):
            resp = client.post(_URL, json={"task": "x"})
            if resp.status_code == 200:
                return str(resp.json()["result"])
        return "gave up"


def _flaky(monkeypatch: pytest.MonkeyPatch, *, fail_times: int) -> None:
    state = {"n": 0}

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        if i < fail_times:
            return httpx.Response(503, json={"error": "temporarily unavailable"}, request=request)
        return httpx.Response(200, json={"result": "done"}, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)


def test_retry_loop_records_and_replays_failures_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _flaky(monkeypatch, fail_times=2)  # two 503s, then a 200

    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="openai", model="m") as cap:
        assert _retry_agent() == "done"
    assert cap.cassette is not None
    assert cap.run_id is not None

    boundaries = cap.cassette.boundaries
    # Three POSTs to the same endpoint — two recorded failures then success, captured in order.
    assert [b.response["status"] for b in boundaries] == [503, 503, 200]
    # The occurrence index climbs for the repeated endpoint: call #0, #1, #2.
    assert occurrences(boundaries) == [0, 1, 2]
    assert [b.occurrence for b in boundaries] == [0, 1, 2]

    # Replay 20x: the recorded 503s are served back in the same order (kill-switch on),
    # so the agent retries exactly as it did live — bit-exact.
    result = verify_run(cap.cassette, _retry_agent, n=20)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1
    store.close()


def test_reordered_retry_is_caught_as_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If replay reaches the endpoint a different number of times, it fails loud (never silent)."""
    _flaky(monkeypatch, fail_times=1)  # one 503, then 200 → two boundaries recorded
    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="openai", model="m") as cap:
        _retry_agent()
    assert cap.cassette is not None

    def _one_shot() -> str:
        with httpx.Client() as client:
            return str(client.post(_URL, json={"task": "x"}).json())

    # A changed agent that calls once can't consume the recorded second boundary → loud failure.
    result = verify_run(cap.cassette, _one_shot, n=1)
    assert not result.passed
    store.close()
