"""Reproducible Month 4 labeled-pair accuracy and actual MCP fleet faithfulness."""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.month4_pairs import pairs

from flightrecorder.dashboard import render_dashboard
from flightrecorder.diagnosis import diagnose
from flightrecorder.integrations.fleet import MCPServer, open_fleet
from flightrecorder.offline import offline_guard
from flightrecorder.portable import export_run
from flightrecorder.replay import record, verify


def fleet_gate(output: Path, repeats: int) -> dict:
    server = Path(__file__).resolve().parents[1] / "examples/month4_mcp_server.py"
    markers = [output / "stdio-effects.txt", output / "http-effects.txt"]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            str(server),
            "--transport",
            "streamable-http",
            "--port",
            str(port),
            "--marker",
            str(markers[1]),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline or process.poll() is not None:
                    raise RuntimeError("MCP HTTP fixture did not become ready") from None
                time.sleep(0.05)
        specs = [
            MCPServer("stdio", "stdio", sys.executable, [str(server), "--marker", str(markers[0])]),
            MCPServer("http", "streamable-http", f"http://127.0.0.1:{port}/mcp"),
        ]

        def run(session, transport):
            async def agent():
                async with open_fleet(session, specs) as fleet:
                    values = await fleet.gather(
                        [
                            ("stdio", "add", {"a": 20, "b": 22, "delay": 0.02}),
                            ("http", "add", {"a": 10, "b": 7}),
                            ("stdio", "fail", {}),
                        ]
                    )
                    assert values[-1]["isError"]
                    return json.dumps(values, sort_keys=True)

            return asyncio.run(agent())

        recording = record(
            run, concurrent=True, provider="mcp-fleet", model="stdio+streamable-http"
        )
    finally:
        process.terminate()
        process.wait(timeout=5)
    before = [p.read_text() for p in markers]
    with (
        patch("subprocess.Popen", side_effect=AssertionError("replay launched a process")),
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=AssertionError("replay launched a process"),
        ),
        offline_guard() as audit,
    ):
        result = verify(recording, run, repeats)
    assert result.passed, result.detail
    assert not audit.blocked_operations
    assert [p.read_text() for p in markers] == before
    wire = [b.response["wire"] for b in recording.boundaries if b.kind == "async-result"]
    calls = sum(
        frame["direction"] == "request" and frame["frame"].get("method") == "tools/call"
        for frames in wire
        for frame in frames
    )
    assert calls == 3
    for frames in wire:
        sent = {f["frame"]["id"] for f in frames if f["direction"] == "request"}
        received = {f["frame"]["id"] for f in frames if f["direction"] == "response"}
        assert sent == received
    export_run(recording, output / "fleet.rewind.json")
    return {
        "source": "actual local MCP servers",
        "transports": ["stdio", "streamable-http"],
        "servers": 2,
        "replays": result.runs,
        "passed": result.passed,
        "wire_tool_calls": calls,
        "wire_ids_match": True,
        "zero_replay_network_or_processes": True,
        "replay_effects": 0,
        "boundaries": len(recording.boundaries),
        "fingerprint": recording.fingerprint,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month4"))
    parser.add_argument("--replays", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.replays <= 1000:
        parser.error("replays must be 1..1000")
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, left, right, expected in pairs():
        report = diagnose(left, right)
        first = report["primary_difference"]
        prediction = {
            "category": first["category"] if first else None,
            "a": first["a"] if first else None,
            "b": first["b"] if first else None,
        }
        correct = all(prediction[key] == expected[key] for key in prediction)
        results.append(
            {
                "case": name,
                "expected": expected,
                "observed": prediction,
                "passed": correct,
                "method": report["comparison_method"],
                "hash_comparisons": report["hash_search"]["comparisons"],
            }
        )
        if name == "insert":
            render_dashboard(
                {"Baseline": left, "With insertion": right}, args.output / "alignment.html"
            )
    fleet = fleet_gate(args.output, args.replays)
    report = {
        "dataset_source": "controlled synthetic edits, not production root-cause accuracy",
        "cases": results,
        "case_count": len(results),
        "correct": sum(row["passed"] for row in results),
        "accuracy": sum(row["passed"] for row in results) / len(results),
        "fleet": fleet,
        "human_review": {"status": "pending", "required_by": "M4.2"},
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"case_count": report["case_count"], "correct": report["correct"], "fleet": fleet},
            indent=2,
        )
    )
    assert all(row["passed"] for row in results), "labeled pair regression; inspect report.json"


if __name__ == "__main__":
    main()
