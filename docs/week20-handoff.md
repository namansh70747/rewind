# Week 1–20 implementation handoff

The software candidate implements the core recording, replay, inspection, fork,
diagnosis, MCP and fleet-analysis paths. This is not a claim that all original
weekly exit criteria are accepted: the [evidence ledger](roadmap-status.md)
identifies real-data, human-review and deliberately unsupported scope separately.

## Changes in this pass

- Real MCP v1 integration test drives two stdio servers concurrently, including an
  error response, persists to SQLite, and performs 50 exact offline replays after
  both servers close. Process creation is forbidden during replay; side-effect
  files prove tools were invoked only during recording.
- Failure maps now navigate from clusters to runs, nearest neighbors and recorded
  boundary timelines. Neighbors use cosine distance in the original feature space,
  never distances in the two-dimensional display. Both TF-IDF and BGE reports use
  the same interaction. Keyboard and narrow-screen navigation are supported.
- Timeline previews are redacted, limited to 200 boundaries per run and 4,000
  characters per request/response. The UI states these limits; full evidence stays
  in the original local recording. Reports contain recorded evidence and should
  receive the same privacy review as exports.
- `fr run-features RUN_ID` exports `rewind.run-features.v1`: boundary counts,
  tool histograms, captured status/finish reasons and non-stream token usage.
  Unknown cost, retry count and divergence remain null with measurement notes.
  Repeated calls alone do not prove a retry. Feature exports also appear in the map.
- Snapshot intervals explicitly reject zero, negatives and booleans.

## Run locally

```bash
uv sync --frozen --extra dev --extra docs --extra integrations --extra tui --extra ml
uv run python scripts/validate_candidate.py
uv run fr demo
uv run fr runs
uv run fr run-features RUN_ID --output .rewind/features.json
uv run fr fleet-map --output .rewind/fleet.json
# Optional BGE path: an already downloaded local model is required.
uv run fr index-embeddings LOCAL_MODEL_DIRECTORY
```

`fleet-map` needs at least three saved runs. Open its adjacent HTML file directly;
all interactions work offline. Existing older reports can still open, but must be
regenerated to contain neighbors and timeline evidence.

## Acceptance still requiring evidence

Weeks 1–20 still require the specified live-provider corpus, long-run measurements,
approved spike/format decisions, reviewed diagnosis pairs, and human assessment of
neighbor relevance and cluster coherence on actual workloads. No local synthetic
fixture or model-generated summary substitutes for these judgments. The original
roadmap's “any MCP server” wording exceeds the implemented MCP v1 client contract;
server-initiated callbacks and SDK v2 are not supported.

Independent Code Owner approval is required by CONTRIBUTING before merge. The
candidate remains in draft PR #43; no release, tag or package publication is implied.
