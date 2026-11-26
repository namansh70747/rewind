"""Failed replay correctness must not qualify a fast benchmark."""

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest


def test_fast_failed_replays_do_not_qualify(monkeypatch: pytest.MonkeyPatch) -> None:
    namespace = runpy.run_path("scripts/validate_month6_performance.py")
    measure = namespace["measure_replay_performance"]
    real_benchmark = measure.__globals__["benchmark_replay"]

    def broken_replay(cassette: Any, run_fn: Any, **kwargs: Any) -> Any:
        return real_benchmark(cassette, lambda *_: "wrong-output", **kwargs)

    monkeypatch.setitem(measure.__globals__, "benchmark_replay", broken_replay)
    report = measure()
    assert report["passed"] is False
    assert report["failed_replays"] == 50
