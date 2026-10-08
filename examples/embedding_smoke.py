"""Qualify a local model + LanceDB/UMAP stack using clearly synthetic recordings.

Usage: python examples/embedding_smoke.py /path/to/bge-small-en-v1.5
The embeddings extra and a previously downloaded local model are required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.diagnosis import diagnose
from flightrecorder.fleet import embedding_index, search_embeddings
from flightrecorder.fleet_view import render_fleet

model = Path(sys.argv[1])
runs = {}
for kind, status in [("timeout", 504), ("rate-limit", 429), ("success", 200)]:
    for i in range(5):
        session = Session("record")
        session.mediate("tool", kind, {"attempt": i}, lambda status=status: {"status": status})
        runs[f"{kind}-{i}"] = Cassette(
            session.boundaries, session.chain, str(status), metadata={"simulated": True}
        )
index = Path(".rewind/qualified-vectors")
report = embedding_index(runs, index, model)
report["qualification"] = (
    "CPU runtime smoke on 15 synthetic recordings; no real fleet or human quality evaluation"
)
report["neighbors"] = search_embeddings(runs["timeout-0"], index, report["table"], model)
assert all(row["id"].startswith("timeout-") for row in report["neighbors"])
report["semantic_alignment"] = diagnose(runs["timeout-0"], runs["rate-limit-0"], model_path=model)[
    "alignment_method"
]
Path(".rewind/embedding-qualification.json").write_text(json.dumps(report, indent=2))
render_fleet(report, Path(".rewind/embedding-map.html"))
print("PASS local encoding, persisted cosine search, HDBSCAN/UMAP and semantic alignment.")
