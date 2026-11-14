"""Benchmark and inspect actual portable recordings; output contains metadata only."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

from textual.widgets import Static

from flightrecorder.interop import write_trace
from flightrecorder.portable import import_run
from flightrecorder.snapshots import SnapshotIndex
from flightrecorder.tui import TimelineApp


async def review(path: Path, output: Path) -> dict:
    cassette = import_run(path)
    count = len(cassette.boundaries)
    if not count:
        raise ValueError("corpus recordings must contain boundaries")
    benchmarks = []
    # Reference states are computed by a separate sequential fold, not the index.
    observed, state, expected = {}, None, []
    for boundary in cassette.boundaries:
        observed[f"{boundary.kind}:{boundary.key}"] = boundary.response
        if boundary.kind == "state":
            state = boundary.response
        expected.append((observed.copy(), state))
    for interval in sorted({1, max(1, math.isqrt(count)), count}):
        started = time.perf_counter_ns()
        index = SnapshotIndex(cassette, interval)
        cold = time.perf_counter_ns() - started
        timings, work = [], []
        for query in range(100):
            at = query * 7919 % count
            started = time.perf_counter_ns()
            result = index.at(at)
            timings.append((time.perf_counter_ns() - started) / 1000)
            assert (result["observed"], result["agent_snapshot"]) == expected[at]
            assert result["replayed_events"] < interval
            work.append(result["replayed_events"])
        benchmarks.append(
            {
                "interval": interval,
                "checkpoints": len(index.checkpoints),
                "cold_build_us": cold / 1000,
                "warm_p50_us": statistics.median(timings),
                "warm_p95_us": sorted(timings)[94],
                "max_suffix_events": max(work),
                "exact_states": True,
            }
        )
    app = TimelineApp(cassette)
    positions = []
    async with app.run_test(size=(120, 45)) as pilot:
        for at in [*range(count), *range(count - 2, -1, -1)]:
            while app.position < at:
                await pilot.press("right")
            while app.position > at:
                await pilot.press("left")
            rendered = json.loads(str(app.query_one("#event", Static).content))
            assert rendered["boundary"]["seq"] == at
            assert rendered["boundary"]["chain_hash"] == cassette.boundaries[at].chain_hash
            assert (rendered["state"]["observed"], rendered["state"]["agent_snapshot"]) == expected[
                at
            ]
            positions.append(at)
        app.position = next((b.seq for b in cassette.boundaries if b.kind == "http"), 0)
        app.render_event()
        await pilot.pause()
        app.save_screenshot(
            f"{cassette.provider}-{cassette.fingerprint[:12]}.svg", path=str(output)
        )
    trace = output / f"{cassette.provider}-{cassette.fingerprint[:12]}.perfetto"
    write_trace(cassette, trace, "perfetto")
    return {
        "provider": cassette.provider,
        "model": cassette.model,
        "fingerprint": cassette.fingerprint,
        "boundaries": count,
        "counterfactual": bool(cassette.metadata.get("counterfactual")),
        "scrub_positions": positions,
        "rendered_state_exact": True,
        "all_io_and_hashes_visible": True,
        "benchmarks": benchmarks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month3-corpus-review"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    reports = [asyncio.run(review(path, args.output)) for path in args.recordings]
    (args.output / "report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
