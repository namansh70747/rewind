"""Synthetic local measurements for Month 6; no production approval is implied.

Measures:
1. Boundary capture overhead per event.
2. Replay throughput (concurrent N-way execution).
3. Sqrt-N snapshot reconstruction latency.
4. Content-addressed storage (BLAKE3 + zstd) compression and deduplication ratio.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import tempfile
import time
from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.month6 import benchmark_replay
from flightrecorder.snapshots import SnapshotIndex
from flightrecorder.store import RunStore


def measure_interception_overhead(iterations: int = 1000) -> dict:
    """Measure raw boundary mediation overhead compared to uninstrumented callable."""

    def fn() -> dict:
        return {"status": 200, "data": "payload-value"}

    # Baseline uninstrumented
    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        fn()
    baseline_ns = (time.perf_counter_ns() - t0) / iterations

    # Mediated in Session("record")
    session = Session("record")
    t0 = time.perf_counter_ns()
    for i in range(iterations):
        session.mediate("tool", f"tool_{i % 10}", {"arg": i}, fn)
    mediated_ns = (time.perf_counter_ns() - t0) / iterations

    overhead_us = (mediated_ns - baseline_ns) / 1000.0
    return {
        "iterations": iterations,
        "baseline_us": round(baseline_ns / 1000.0, 3),
        "mediated_us": round(mediated_ns / 1000.0, 3),
        "overhead_us_per_boundary": round(overhead_us, 3),
    }


def measure_replay_performance() -> dict:
    """Measure offline replay throughput using multi-threaded concurrent replay."""
    session = Session("record")
    for i in range(5):
        session.mediate("tool", f"step_{i}", {"seq": i}, lambda: {"ok": True})
    cassette = Cassette(session.boundaries, session.chain, "final-output", "", "", {})

    def replay_fn(s: Session, _transport: object) -> str:
        for i in range(5):
            s.mediate("tool", f"step_{i}", {"seq": i}, lambda: {"ok": True})
        return "final-output"

    result = benchmark_replay(cassette, replay_fn, n=50, max_workers=8)
    return {
        "n_replays": result["n_replays"],
        "throughput_replays_per_s": result["throughput_replays_per_s"],
        "elapsed_s": result["elapsed_s"],
        "passed_replays": result["passed"],
        "failed_replays": result["failed"],
        "passed": result["failed"] == 0 and result["passed"] == result["n_replays"],
    }


def measure_storage_efficiency() -> dict:
    """Measure BLAKE3 + zstd compression and deduplication on repeated payloads."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "perf.db")
        store = RunStore(db_path)
        try:
            # 20 runs sharing system prompt and repeated tool outputs
            common_prompt = {
                "role": "system",
                "content": "You are a helpful assistant with lots of context. " * 50,
            }
            for _run_idx in range(20):
                s = Session("record")
                s.mediate(
                    "http",
                    "POST /v1/chat",
                    common_prompt,
                    lambda: {"status": 200, "body": {"text": "ok"}},
                )
                s.mediate("tool", "calc", {"x": 1}, lambda: {"result": 42})
                store.save(Cassette(s.boundaries, s.chain))

            stats = store.storage_stats()
        finally:
            store.close()

    raw_estimate_bytes = 20 * (len(json.dumps(common_prompt)) + 200)
    compressed_bytes = stats["compressed_bytes"]
    ratio = compressed_bytes / raw_estimate_bytes if raw_estimate_bytes > 0 else 1.0

    return {
        "runs_saved": 20,
        "unique_blobs": stats["unique_blobs"],
        "references": stats["references"],
        "compressed_bytes": compressed_bytes,
        "raw_estimate_bytes": raw_estimate_bytes,
        "compression_ratio": round(ratio, 3),
        "dedup_effective": stats["unique_blobs"] < stats["references"],
        "passed": stats["unique_blobs"] < stats["references"],
    }


def measure_snapshot_latency(steps: int = 256) -> dict:
    """Measure state recovery latency across sqrt-N checkpoint intervals."""
    s = Session("record")
    for step in range(steps):
        s.mediate("state", "agent", None, lambda step=step: {"step": step})
    cassette = Cassette(s.boundaries, s.chain)

    interval = max(1, math.isqrt(steps))
    index = SnapshotIndex(cassette, interval)
    latencies_us = []
    for q in range(50):
        target = (q * 37) % steps
        t0 = time.perf_counter_ns()
        index.at(target)
        latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)

    p95_us = sorted(latencies_us)[int(len(latencies_us) * 0.95)]
    return {
        "steps": steps,
        "checkpoint_interval": interval,
        "p95_latency_us": round(p95_us, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".rewind/month6/synthetic-performance.json")
    )
    args = parser.parse_args()
    replay = measure_replay_performance()
    storage = measure_storage_efficiency()
    if not replay["passed"] or not storage["passed"]:
        raise RuntimeError("Synthetic replay correctness or deduplication check failed")
    report = {
        "schema": "rewind.synthetic-performance.v1",
        "source": "Synthetic in-memory boundary workload and repeated storage payloads",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "interception": measure_interception_overhead(),
        "replay": replay,
        "storage": storage,
        "snapshot": measure_snapshot_latency(),
        "qualification": "Local diagnostic measurements only. Production qualification requires target workloads and an agreed budget; no human approval is asserted.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
