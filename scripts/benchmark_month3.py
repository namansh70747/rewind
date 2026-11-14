"""Measure warm snapshot reconstruction for a synthetic long recording.

Cold index construction is reported separately; copying returned state still costs
O(state size). replayed_events measures suffix work, not total wall-time complexity.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.snapshots import SnapshotIndex


def benchmark(steps: int = 1024, queries: int = 200) -> dict:
    session = Session("record")
    for step in range(steps):
        session.mediate("state", "agent", None, lambda step=step: {"step": step})
    cassette = Cassette(session.boundaries, session.chain)
    results = []
    for interval in sorted({1, max(1, math.isqrt(steps)), steps}):
        started = time.perf_counter_ns()
        index = SnapshotIndex(cassette, interval)
        build_ms = (time.perf_counter_ns() - started) / 1e6
        latencies, suffixes = [], []
        for query in range(queries):
            at = query * 7919 % steps
            started = time.perf_counter_ns()
            result = index.at(at)
            latencies.append((time.perf_counter_ns() - started) / 1000)
            assert result["agent_snapshot"] == {"step": at}
            assert result["replayed_events"] < interval
            suffixes.append(result["replayed_events"])
        results.append(
            {
                "interval": interval,
                "checkpoints": len(index.checkpoints),
                "cold_build_ms": build_ms,
                "warm_p50_us": statistics.median(latencies),
                "warm_p95_us": sorted(latencies)[math.ceil(queries * 0.95) - 1],
                "max_suffix_events": max(suffixes),
                "exact_state": True,
            }
        )
    return {
        "source": "synthetic",
        "steps": steps,
        "queries_per_interval": queries,
        "default_interval": math.isqrt(steps),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=1024)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month3-benchmark.json"))
    args = parser.parse_args()
    if args.steps < 1 or args.queries < 1:
        parser.error("steps and queries must be positive")
    if args.output.exists():
        parser.error("Choose a new output path to preserve prior evidence")
    report = benchmark(args.steps, args.queries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
