# Month 3 implementation validation — 12 November 2026

This is implementation evidence for weeks 10–13, not a claim that every live
production or external-viewer acceptance gate is complete.

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

`NVIDIA_API_KEY` and `GEMINI_API_KEY` are absent from the execution environment.
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
