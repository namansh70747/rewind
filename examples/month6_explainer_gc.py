"""Month 6 — LoRA explainer stub, concurrent replay, and GC walkthrough.

Demonstrates the three new P5 capabilities on a synthetic corpus:

1. ``fr explain`` — deterministic plain-English root-cause narration.
2. ``concurrent_replay`` — replay a cassette N times in parallel.
3. ``retention_gc`` — delete old runs by keep_last or max_age_days.

No model is called.  No API key, database server, or GPU is needed.
Run with:  ``python examples/month6_explainer_gc.py``
"""

from __future__ import annotations

import tempfile

from flightrecorder.boundary import Cassette, Session
from flightrecorder.month5 import record_failure
from flightrecorder.month6 import (
    benchmark_replay,
    concurrent_replay,
    explain,
    retention_gc,
)
from flightrecorder.store import RunStore


def _simple_cassette() -> Cassette:
    session = Session("record")
    session.mediate("tool", "ping", {}, lambda: {"ok": True})
    return Cassette(session.boundaries, session.chain, "pong", "", "", {})


def _replay_fn(session: Session, _transport: object) -> str:
    session.mediate("tool", "ping", {}, lambda: {"ok": True})
    return "pong"


def demo_explain() -> None:
    print("\n=== fr explain (deterministic narration) ===")
    for family in ("tool-error", "transport-timeout", "context-budget"):
        cassette = record_failure(family)
        report = explain(
            cassette,
            classifier_report={"label": family, "probabilities": {family: 0.9}},
            run_id=f"demo-{family}",
        )
        print(f"\nFamily: {family}")
        print(f"  label_source : {report['label_source']}")
        print(f"  cause        : {report['cause'][:90]}...")
        print(f"  next_steps   : {report['next_steps'][0]}")
        print(f"  lora_status  : {report['lora_status']}")


def demo_concurrent_replay() -> None:
    print("\n=== concurrent_replay (10x parallel) ===")
    cassette = _simple_cassette()
    result = concurrent_replay(cassette, _replay_fn, n=10, max_workers=4)
    print(result)

    print("\n=== benchmark_replay (evidence record) ===")
    report = benchmark_replay(cassette, _replay_fn, n=10, max_workers=4)
    print(f"  schema          : {report['schema']}")
    print(f"  passed/total    : {report['passed']}/{report['n_replays']}")
    print(f"  throughput      : {report['throughput_replays_per_s']} replays/s")


def demo_retention_gc() -> None:
    print("\n=== retention_gc (keep_last=1) ===")
    with tempfile.TemporaryDirectory() as tmp:
        db = tmp + "/runs.db"
        store = RunStore(db)
        try:
            for family in ("tool-error", "transport-timeout", "context-budget"):
                run_id = store.save(record_failure(family))
                print(f"  saved {run_id[:16]}…  ({family})")
        finally:
            store.close()

        report = retention_gc(db, keep_last=1)
        print(report)


if __name__ == "__main__":
    demo_explain()
    demo_concurrent_replay()
    demo_retention_gc()
    print("\nMonth 6 demo complete.")
