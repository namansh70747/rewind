# Reproducible sample gallery

All external services in these recordings are simulated. The captures, hash chains,
portable checksums and replay/fork logic are real. No provider qualification or
real customer data is claimed.

| Sample | Scenario | Download |
|---|---|---|
| Failed | Quote 720 exceeds budget 500 | [failed.json](samples/failed.json) |
| Passing | Quote 420 is affordable | [passing.json](samples/passing.json) |
| Recovered | Intervention replaces 720 with 420 | [recovered.json](samples/recovered.json) |

Import a downloaded sample with `fr import failed.json`, then run
`fr verify RUN_ID --n 50`. Use `fr demo` to regenerate all three and the dashboard.

Run `python examples/alignment_demo.py` to inspect an inserted step with the aligned
dashboard. Open `.rewind/alignment.html`; selecting an alignment row reveals both
sides and moves the inspector to the corresponding recorded boundary.
