"""Generate a different-length trajectory comparison without any external service."""

from pathlib import Path

from flightrecorder.boundary import Cassette, Session
from flightrecorder.dashboard import render_dashboard
from flightrecorder.demo import record_demo

baseline = record_demo()
session = Session("record")
for boundary in baseline.boundaries:
    if boundary.seq == 2:
        session.mediate("tool", "extra_check", {}, lambda: {"ok": True})
    session.mediate(boundary.kind, boundary.key, boundary.request, lambda b=boundary: b.response)
candidate = Cassette(
    session.boundaries, session.chain, baseline.final_output, metadata={"simulated": True}
)
render_dashboard(
    {"Baseline": baseline, "With extra step": candidate}, Path(".rewind/alignment.html")
)
print("Open .rewind/alignment.html and select the step-inserted row.")
