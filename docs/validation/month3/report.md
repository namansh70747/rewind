# Month 3 implementation validation — 12 November 2026

Current status: the supported serialized-agent Month 3 gate is validated with
live Gemini and NVIDIA parent/fork runs, exact offline replays, state inspection,
and real Jaeger ingestion/browser checks. The entries below retain the initial
checks and subsequent closeout evidence chronologically. This does not claim
arbitrary concurrent forks, heap restoration, or universal production coverage.

| Planner area | Evidence | Scope / limitation |
| --- | --- | --- |
| Week 10: replay-to-N and snapshots | Existing CAS checkpoints; `show --at` now uses SnapshotIndex; interval sweep below | Boundary-observable state and explicit snapshots, not heap restoration |
| Week 11: scrubber and traces | Headless Textual pilot steps both directions; Perfetto and OTLP JSON/protobuf exports | Viewer-compatible serialization tested; hosted Jaeger/Phoenix not exercised |
| Week 12: counterfactual fork | General script CLI; async mock-only and allowlisted-live APIs; child offline replay tests | Missing mocks fail closed; serialized trusted-agent contract |
| Week 13: LangGraph | Real installed LangGraph async engine records, forks and replays for NVIDIA/Gemini-shaped HTTP | HTTP is synthetic in this session; fresh graph/thread state required |

## Automated checks

- Full pytest suite: 128 passing tests, including eight Month 3 regressions.
- Ruff lint, Ruff format, strict mypy, wheel and source distribution build.
- Two-provider async example: six offline replays per provider, no mutating
  producer invocation in either fork. See [provider-gate.json](provider-gate.json).
- OTLP protobuf is decoded with the official ExportTraceServiceRequest schema.
- Test fixtures and benchmark are explicitly synthetic; no private production
  recordings or API keys are committed.

## Snapshot measurements

[Raw measurements](snapshot-benchmark.json): 1,024 boundaries, 200 random-access
queries per interval, on this development executor. These are observations,
not CI latency thresholds or a production-corpus claim.

| Interval | Checkpoints | Cold build (ms) | Warm p50 (µs) | Warm p95 (µs) | Maximum suffix events |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,024 | 19.87 | 5.57 | 7.07 | 0 |
| 32 (default) | 32 | 19.40 | 8.56 | 13.62 | 31 |
| 1,024 | 1 | 18.29 | 88.67 | 262.54 | 969 |

All inspected states matched the requested step. The sqrt(N) default retains
32 checkpoints instead of 1,024 while bounding this fixture's suffix to 31 events.
Larger/growing state payloads still incur return-copy costs.

## Live provider status

`NVIDIA_API_KEY` and `GEMINI_API_KEY` were absent from the development environment.
The follow-up GitHub Actions credential preflight also found both repository
secrets unavailable; the live acceptance job correctly fails rather than passing
on synthetic evidence.
The `--live` preflight was run and correctly exited before network calls or output
directory creation, naming both missing variables. No live provider response,
quota availability, or model access is claimed. Configure both securely in the
process environment and run:

```bash
uv run python examples/month3_langgraph.py --live --output .rewind/month3-live
```

This executes parent and live-fork completions for each provider, then verifies
both recordings offline. The dangerous reservation producer remains mocked.

## Rewind versus native LangGraph time travel

A LangGraph checkpoint resume recomputes later graph nodes and may call external
services again. Rewind's replay executes graph logic with previously recorded
external results and compares the full hash-chain. Rewind's fork changes one
boundary, then uses explicit mocks or separately authorized live producers.
Native checkpoint restoration is not implemented by this state-stream adapter;
recording/replay must start from fresh thread state. Concurrent forks are rejected.

## Follow-up acceptance — 13 November 2026 (India time)

[Acceptance run 43281845138](https://github.com/namansh70747/rewind/actions/runs/43281845138)
executed the exports against a real Jaeger 1.76 collector and query service:

- Four traces ingested from the existing exports without payload rewriting:
  two OTLP/HTTP JSON parents and two protobuf forks.
- Seven spans per trace (28 total) retrieved from Jaeger's query API.
- Operation names, boundary chain hashes, counterfactual labels and parent
  fingerprints matched the exports.
- Chromium opened a trace in Jaeger's UI and found the quote span.
- A JSON report and browser screenshot are retained in the
  [viewer evidence artifact](https://github.com/namansh70747/rewind/actions/runs/43281845138/artifacts/13974150506).
  The trace content is synthetic; the collector and browser are real.

The new Month 3 acceptance workflow repeats this viewer check for PRs. Its
separate live job reads only repository secrets, never writes credentials into
recordings, and uploads metadata-only live evidence. It remains blocked until
both secrets are configured in Actions settings. Re-run the failed live job
after configuring them. No merge is needed to re-run an existing job.

Month 3 is not declared fully accepted until that live job passes. Concurrent
fork scheduling and arbitrary heap/checkpointer restoration remain outside the
documented serialized-agent contract rather than silently claimed as supported.

## Live Gemini acceptance — 13 November 2026 (India time)

A user-supplied credential authenticated successfully with Gemini's models API.
The credential was used only in the process environment, never committed.
The old gemini-2.5-flash default returned a model-retirement error. The current
Flash model returned HTTP 503 with a high-demand message, so validation used
an available smaller model, gemini-3.5-flash-lite, selected explicitly.

[Live metadata report](gemini-live.json):

- A real Gemini-backed async LangGraph parent and counterfactual fork completed.
- Parent and fork each passed three exact offline replays (six total), including
  final-output and full boundary-chain comparisons.
- Seven boundaries were recorded in the parent; all states were reconstructible.
- The mutating reservation producer ran zero times in the fork.
- Both recordings exported as portable recordings, Perfetto, OTLP JSON and OTLP
  protobuf. Full prompt/response recordings remain local; this committed report
  contains only provider/model identifiers, fingerprints and validation counts.

This closes the real-provider LangGraph record/replay/fork portion of the Month 3
core gate using Gemini. Jaeger ingestion/browser validation was completed above.
NVIDIA live validation is still outstanding because no NVIDIA key is configured.
GitHub Actions also still needs repository secrets for repeatable live CI runs;
the session credential has not been stored in GitHub.

Reproduce Gemini independently:

```bash
uv run python examples/month3_langgraph.py --live --provider gemini --model gemini-3.5-flash-lite --output .rewind/gemini-live
```

## Final two-provider closeout — 13 November 2026 (India time)

Both credentials were supplied for this session and used only in process memory.
[Combined live report](live-provider-gate.json) and [NVIDIA report](nvidia-live.json):

| Provider | Successfully exercised model | Exact offline replays | Mutating fork calls |
| --- | --- | ---: | ---: |
| Gemini | gemini-3.5-flash-lite | 6 | 0 |
| NVIDIA | nvidia/nemotron-3.5-bolt-e4b | 6 | 0 |

NVIDIA's previous llama-3.1-8b default returned HTTP 410. Its current model
catalog and a successful live request confirmed the Bolt model. Provider
defaults now use the models actually validated in this session. Gemini also
supports an explicit model override when another model is available to the user.

Each provider completed a real async LangGraph parent and safe live fork,
three offline replays per recording, state reconstruction and all four export
formats. Imported parent/fork bundles had valid integrity and actual nonempty
model text. Changed files and generated recordings were checked for both literal
credentials; neither appeared. Only metadata reports are committed.

The earlier missing-session-credential blocker is resolved. GitHub Actions still
needs its own repository secrets for repeatable live CI; session credentials were
not persisted to GitHub. The existing strict live CI preflight will remain blocked
until those secrets are configured. Local live acceptance is complete, while that
CI provisioning status remains separate and explicit.
