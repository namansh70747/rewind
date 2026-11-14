"""Live NVIDIA check using only hand-authored synthetic public inputs."""

from __future__ import annotations

import argparse
import json
import os
from functools import partial
from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.diagnosis import diagnose
from flightrecorder.semantic import embed_pair, load_vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".rewind/month4-embeddings"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)

    def recording(extra: bool) -> Cassette:
        session = Session("record")
        events = [("search", {"q": "affordable graphics card"}, ["synthetic result"])]
        if extra:
            events.append(("inspect", {"item": "synthetic graphics card"}, True))
        events.append(("finish", {}, "done"))
        for key, request, response in events:
            session.mediate("tool", key, request, partial(lambda value: value, response))
        return Cassette(session.boundaries, session.chain, "done", provider="synthetic")

    a, b = recording(False), recording(True)
    cache = embed_pair(a, b, os.environ.get("NVIDIA_API_KEY", ""))
    vectors = load_vectors(cache, a, b)
    report = diagnose(a, b, vectors=vectors)
    first = report["primary_difference"]
    assert (first["a"], first["b"], first["category"]) == (None, 1, "step-inserted")
    # Export metadata only. Input text above is public; keys never enter a cassette.
    summary = {
        "source": "live NVIDIA embeddings of hand-authored synthetic inputs only",
        "private_recording_inputs_sent": False,
        "provider": "nvidia",
        "model": cache["model"],
        "vectors": [len(vectors[0]), len(vectors[1])],
        "dimensions": len(vectors[0][0]),
        "alignment_method": report["alignment_method"],
        "observed": {"a": first["a"], "b": first["b"], "category": first["category"]},
        "passed": True,
    }
    (args.output / "report.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
