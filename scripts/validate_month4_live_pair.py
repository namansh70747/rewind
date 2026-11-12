"""Semantic diagnosis of actual provider recordings; human agreement stays explicit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from flightrecorder.dashboard import render_dashboard
from flightrecorder.diagnosis import diagnose
from flightrecorder.portable import import_run
from flightrecorder.semantic import embed_pair, load_vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("passing", type=Path)
    parser.add_argument("failing", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month4-real-pair"))
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Explicitly send canonical recorded inputs to NVIDIA; requires disclosure approval",
    )
    args = parser.parse_args()
    left, right = import_run(args.passing), import_run(args.failing)
    if args.output.exists():
        parser.error("choose a new output directory to preserve evidence")
    args.output.mkdir(parents=True)
    cache, vectors = None, None
    if args.embed:
        cache = embed_pair(left, right, os.environ.get("NVIDIA_API_KEY", ""))
        (args.output / "private-vectors.json").write_text(json.dumps(cache), encoding="utf-8")
        vectors = load_vectors(cache, left, right)
    report = diagnose(left, right, vectors=vectors)
    first = report["primary_difference"]
    assert first and first["category"] == "tool-result-drift"
    passed, failed = json.loads(left.final_output), json.loads(right.final_output)
    assert passed["price"] <= 500 < failed["price"]
    assert first["left"]["key"] == first["right"]["key"] == "month3.quote"
    render_dashboard(
        {"Passing quote": left, "Failing quote": right},
        args.output / "review.html",
        alignment_vectors=vectors,
    )
    summary = {
        "source": "actual provider parent and controlled live counterfactual fork",
        "provider": left.provider,
        "model": left.model,
        "passing_fingerprint": left.fingerprint,
        "failing_fingerprint": right.fingerprint,
        "embedding_provider": "nvidia" if cache else None,
        "embedding_model": cache["model"] if cache else None,
        "vectors": [len(vectors[0]), len(vectors[1])] if vectors else None,
        "dimensions": len(vectors[0][0]) if vectors else None,
        "private_input_embedding": "requested" if cache else "not sent; offline comparison",
        "alignment_method": report["alignment_method"],
        "first_decision": {
            k: first[k] for k in ("a", "b", "category", "input_relation", "summary")
        },
        "review_case": {
            "same_tool_input": True,
            "passing_quote": passed["price"],
            "failing_quote": failed["price"],
            "budget": 500,
            "proposed_name": "Tool result changed before the model continuation",
        },
        "human_review": {
            "status": "pending",
            "required_by": "M4.2",
            "question": "Does the named difference agree with the two recorded quote results?",
        },
    }
    (args.output / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
