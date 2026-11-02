"""Run actual local Ollama inference on explicitly synthetic cluster evidence.

Start Ollama and download a model yourself before running this example. No model
is pulled by this script, and generated summaries still require human review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.fleet_view import render_fleet
from flightrecorder.summaries import summarize_clusters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, default=Path(".rewind/ollama-qualification.json"))
    args = parser.parse_args()
    runs = {}
    points = []
    for cluster, (kind, status) in enumerate(
        [("timeout", 504), ("rate-limit", 429), ("success", 200)]
    ):
        for i in range(5):
            session = Session("record")
            session.mediate("tool", kind, {"attempt": i}, lambda status=status: {"status": status})
            rid = f"{kind}-{i}"
            runs[rid] = Cassette(
                session.boundaries, session.chain, str(status), metadata={"simulated": True}
            )
            points.append({"id": rid, "cluster": cluster, "x": cluster * 5 + i, "y": i})
    report = summarize_clusters(
        {
            "points": points,
            "qualification": "Actual local inference on synthetic, manually grouped fixtures; not real fleet quality.",
            "projection": "fixed fixture coordinates, not UMAP",
            "human_evaluation": "pending",
        },
        runs,
        args.model,
        args.endpoint,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_fleet(report, args.output.with_suffix(".html"))
    passed = all(row["status"] == "generated" for row in report["summaries"].values())
    print(f"{'PASS' if passed else 'FAIL'}: three cluster summaries; human review remains required")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
