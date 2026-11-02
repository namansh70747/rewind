"""Replay-as-fixture gate and measured local performance; no claimed provider evidence."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from .boundary import Cassette, Session
from .portable import import_run
from .redaction import redact_text
from .scripts import verify_script
from .snapshots import SnapshotIndex
from .store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def evaluate_manifest(manifest: Path, repeats: int = 5) -> dict[str, Any]:
    """Execute only trusted scripts referenced by the user-provided fixture manifest."""
    if type(repeats) is not int or not 1 <= repeats <= 1000:
        raise ValueError("repeats must be an integer between 1 and 1000")
    if manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("manifest exceeds 4 MiB limit")
    rows = json.loads(manifest.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest must be a non-empty JSON list")
    # Validate the entire manifest before executing even the first trusted script.
    base = manifest.resolve().parent
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(key), str) and row[key] for key in ("recording", "script")
        ):
            raise ValueError("each fixture needs non-empty recording and script paths")
        pair = tuple(str((base / row[key]).resolve()) for key in ("recording", "script"))
        if any(
            not (base / row[key]).resolve().is_relative_to(base) for key in ("recording", "script")
        ):
            raise ValueError("fixture paths must stay inside the manifest directory")
        identity = (pair[0], pair[1])
        if identity in seen:
            raise ValueError("duplicate fixture would inflate corpus evidence")
        seen.add(identity)
    results = []
    for row in rows:
        try:
            cassette = import_run(manifest.parent / row["recording"])
            result = verify_script(cassette, manifest.parent / row["script"], repeats)
            results.append(
                {
                    "recording": row["recording"],
                    "passed": result.passed,
                    "detail": result.detail,
                    "replays_completed": result.runs,
                    "boundaries": len(cassette.boundaries),
                    "fingerprint": cassette.fingerprint,
                    "source_sha256": cassette.metadata.get("source_sha256"),
                    "provenance": "unverified; replay success does not establish real-provider origin",
                }
            )
        except (Exception, SystemExit) as exc:
            results.append(
                {
                    "recording": row["recording"],
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "detail": redact_text(str(exc)),
                }
            )
    return {
        "passed": all(r["passed"] for r in results),
        "requested_replays": repeats,
        "fixture_count": len(results),
        "unique_recording_fingerprints": len(
            {row["fingerprint"] for row in results if "fingerprint" in row}
        ),
        "fixtures": results,
    }


def benchmark(db_path: Path, steps: int = 1000) -> dict[str, Any]:
    if not 10 <= steps <= 100_000:
        raise ValueError("steps must be between 10 and 100000")
    payload = {"price": 420, "status": "ok"}
    start = time.perf_counter_ns()
    for _ in range(steps):
        dict(payload)
    baseline = time.perf_counter_ns() - start
    session = Session("record")
    start = time.perf_counter_ns()
    for i in range(steps):
        session.mediate("tool", "quote", {"index": i}, lambda: payload)
    capture_ns = time.perf_counter_ns() - start
    cassette = Cassette(session.boundaries, session.chain)
    start = time.perf_counter_ns()
    index = SnapshotIndex(cassette)
    index_ns = time.perf_counter_ns() - start
    start = time.perf_counter_ns()
    for i in range(0, steps, max(1, steps // 100)):
        index.at(i)
    query_ns = time.perf_counter_ns() - start
    store = RunStore(db_path)
    try:
        first = store.save(cassette)
        blobs = store.blob_count()
        store.save(cassette)
        stats = store.storage_stats()
        dedup = store.blob_count() == blobs
    finally:
        store.close()
    return {
        "workload": "synthetic small JSON tool; not LLM latency or production overhead",
        "steps": steps,
        "baseline_ns": baseline,
        "capture_ns": capture_ns,
        "capture_ns_per_boundary": capture_ns / steps,
        "index_build_ns": index_ns,
        "query_batch_ns": query_ns,
        "snapshot_interval": index.interval,
        "second_save_deduplicated": dedup,
        "storage": stats,
        "run_id": first,
        "acceptable_threshold": "not specified; human performance gate required",
    }
