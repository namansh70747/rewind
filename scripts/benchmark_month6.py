"""Measure baseline vs capture overhead; do not claim production acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flightrecorder.boundary import Session
from flightrecorder.month6 import concurrent_replay
from flightrecorder.replay import record


def run(session: Session | None, transport: object = None) -> str:
    values = []
    for i in range(12):

        def producer(i: int = i) -> str:
            value = str(i).encode()
            for _ in range(1500):
                value = hashlib.sha256(value).digest()
            return value.hex()

        values.append(
            producer() if session is None else session.mediate("tool", f"compute-{i}", {}, producer)
        )
    return json.dumps(values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month6/performance.json"))
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("need at least 3 samples")
    baseline, captured = [], []
    expected = run(None)
    for index in range(args.samples):
        # Alternate order to reduce systematic warm-cache bias.
        for mode in ("baseline", "capture") if index % 2 else ("capture", "baseline"):
            started = time.perf_counter()
            value = run(None) if mode == "baseline" else record(run).final_output
            elapsed = time.perf_counter() - started
            assert value == expected
            (baseline if mode == "baseline" else captured).append(elapsed * 1000)
    cassette = record(run)
    verified = concurrent_replay(cassette, run, n=50, max_workers=4)
    assert verified.passed == 50 and verified.failed == 0
    report = {
        "schema": "rewind.capture-benchmark.v1",
        "source": "controlled CPU-bound 12-tool workload, not production fleet",
        "samples": args.samples,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "baseline_p50_ms": statistics.median(baseline),
        "capture_p50_ms": statistics.median(captured),
        "capture_to_baseline_p50_ratio": statistics.median(captured) / statistics.median(baseline),
        "capture_added_p50_ms": statistics.median(captured) - statistics.median(baseline),
        "replay_passed": verified.passed,
        "production_acceptance": "pending target fleet measurements and an agreed overhead budget",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
