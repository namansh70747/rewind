"""Measure an installed loopback workspace and verify recovery from a SQLite backup."""

from __future__ import annotations

import argparse
import json
import math
import platform
import sqlite3
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import httpx

from flightrecorder.store import RunStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--requests", type=int, default=400)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 1 <= args.requests <= 2000 and 1 <= args.workers <= 32):
        parser.error("port, requests and workers must be within the documented limits")
    if not args.db.is_file():
        parser.error("the workspace database must exist")
    origin = f"http://127.0.0.1:{args.port}"
    with closing(RunStore(args.db)) as store:
        original = store.load(args.run)
    with httpx.Client(base_url=origin, timeout=15, trust_env=False) as client:
        home = client.get("/")
        home.raise_for_status()
        csp = home.headers.get("content-security-policy", "")
        controls = {
            "denies_framing": "frame-ancestors 'none'" in csp,
            "restricts_browser_connections_to_self": "connect-src 'self'" in csp,
            "requires_mutation_token": client.post("/api/v1/corpus-audit", json={}).status_code
            == 403,
        }

        def read_run(_: int) -> tuple[float, str | None]:
            started = time.perf_counter()
            try:
                response = client.get(f"/api/v1/runs/{args.run}")
                response.raise_for_status()
                if response.json()["run"]["final_output"] != original.final_output:
                    return (time.perf_counter() - started) * 1000, "recorded output mismatch"
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                return (time.perf_counter() - started) * 1000, type(exc).__name__
            return (time.perf_counter() - started) * 1000, None

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as workers:
            reads = list(workers.map(read_run, range(args.requests)))
        elapsed = time.perf_counter() - started

    with tempfile.TemporaryDirectory(prefix="rewind-restore-") as temp:
        backup = Path(temp) / "restored.db"
        with (
            closing(sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(backup)) as destination,
        ):
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        with closing(RunStore(backup)) as restored:
            recovered = restored.load(args.run)

    latencies = sorted(ms for ms, _ in reads)
    errors = [error for _, error in reads if error is not None]
    recovery = {
        "sqlite_integrity_ok": integrity == "ok",
        "fingerprint_matches": recovered.fingerprint == original.fingerprint,
        "final_output_matches": recovered.final_output == original.final_output,
    }
    result = {
        "schema": "rewind.workspace-audit.v1",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "workload": "concurrent read of one installed-workspace recording",
        "run_id": args.run,
        "stress": {
            "requests": len(reads),
            "workers": args.workers,
            "errors": len(errors),
            "error_types": sorted(set(errors)),
            "p50_ms": round(statistics.median(latencies), 3),
            "p95_ms": round(latencies[math.ceil(0.95 * len(latencies)) - 1], 3),
            "requests_per_second": round(len(reads) / elapsed, 2),
        },
        "defensive_controls": controls,
        "backup_recovery": recovery,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if errors or not all(controls.values()) or not all(recovery.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
