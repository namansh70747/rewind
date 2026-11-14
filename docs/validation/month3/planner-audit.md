# Month 3 planner audit

Audited against **every E1/E2/E3 bullet and exit criterion in weeks 10–13** of
`docs/plan/roadmap-6-months.md` and gates M3.1–M3.4 in
`docs/plan/milestones-and-exit-criteria.md`.

## Gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| M3.1: exact inspection at any step of a long run | PASS | 1,024-step fixture; 200 queries per interval; exact state, default k=32, maximum suffix 31; persistent deltas/GC/reopen/legacy tests |
| M3.2: terminal scrubber and Perfetto | PASS | Four real provider recordings, 92 rendered navigation positions; four unchanged files loaded by official Perfetto processor, 48 slices, zero parser errors |
| M3.3: safe saved counterfactual fork | PASS | CLI default simulation and explicit live manifest tests; separately saved quarantined children replay exactly; live provider forks invoke zero mutating tools |
| M3.4: LangGraph record/replay/fork and OTel viewer | PASS | Both live providers use native checkpointers/callbacks; 12 exact offline replays; Jaeger collector/query/browser gate in Actions |

## Requirement-by-requirement mapping

| Week / owner | Planner requirement | Implementation | Verification |
| --- | --- | --- | --- |
| 10 E1 | Nearest snapshot + forward reconstruction | SnapshotIndex; RunStore.snapshot_at | Independent sequential-fold comparison on all four real recordings; long-run and persisted snapshot tests |
| 10 E1 | sqrt(N), COW/incremental CAS deltas | Sparse full anchors, delta manifests, shared response blobs | `test_persisted_snapshot_deltas_schema_gc_and_legacy`; `snapshot-benchmark-final.json` |
| 10 E1 | Schema'd state serialization | state.encode_state/decode_state; versioned logical state and inspection envelope | Pydantic messages supported; opaque types, NaN and unknown versions rejected; ADR-0011 |
| 10 E2 | fr show --at N | Uses persistent snapshots rather than rebuilding the whole index on every CLI call | CLI state/hash test; stable inspection schema |
| 10 E3 | Benchmark corpus and tune k | Corpus interval sweep 1/sqrt(N)/N, separate cold/warm timings | `corpus-review.json`; default sqrt(N) retained for bounded suffix/storage tradeoff, not asserted universally latency-optimal |
| 11 E1 | Stable state API and per-step chain | SnapshotIndex.at, state_at and persisted snapshot_at schema v1 | Exact boundary/request/response/hash comparisons; source-bound cache rejects cross-run substitution |
| 11 E2 | Textual forward/back and prompt/tool inspection | Focusable scroll pane, pinned boundary/hash, left/right and Home/End | Automated pilots on every real recorded step; terminal rendering visually reviewed |
| 11 E2 | Perfetto waterfall export | Complete ordinal slices with request/response/hash/fork args | Official Perfetto trace processor loaded four actual exports unchanged; zero parser errors |
| 11 E3 | Usability pass on real corpus; schema changes via ADR | Four real Gemini/NVIDIA parent/fork runs; pinned hash and keyboard navigation improved after review | `corpus-review.json`; ADR-0011 documents additive sidecars and frozen log compatibility |
| 12 E1 | Replay prefix, one intervention, live continuation | Sync/async fork APIs and explicit policy sessions | Live checkpointed example on both providers; original prefix preserved; model continuation is live |
| 12 E1 | Quarantine, mutating tools mocked, per-tool live opt-in | Script CLI occurrence-aware recorded fixtures; policy-set and --policy; explicit mocks take precedence | Test writes a marker only with explicit live opt-in; unknown/exhausted tools fail closed |
| 12 E2 | fr fork --at, what-if flag and manifest editor | General script CLI, policy-set, terminal and trace provenance | `test_script_cli_defaults_to_tool_simulation_and_manifest_opt_in`; stored child replay tests |
| 12 E3 | Eval-over-forks scaffolding | evaluate_forks with fresh fixtures, one intervention, score, child verification and optional RunStore persistence | `fork-experiments.json`; controlled 420/600 quote trials, no effects |
| 13 E1 | Async completion ordering inside LangGraph | arun_graph + ConcurrentSession with start/result schedule | Real two-branch LangGraph fan-out records fast-before-slow and replays without producers |
| 13 E2 | Native checkpoint/callback adapter | RewindCallback; sync/async capture and restore helpers with explicit completed node and frontier validation | Native existing thread captured; fresh checkpointer restored; wrong frontier rejected; live examples have four callbacks + final checkpoint |
| 13 E2 | OTel/OpenInference export and trace ingest | OTLP JSON/protobuf; HTTP model spans labeled LLM; JSON input/output; trace-only ingest | Official protobuf schema test, trace import non-replayability tests, Jaeger ingestion/query/browser checks |
| 13 E3 | Native resume vs exact Rewind replay artifact | Executed comparison with InMemorySaver and historical checkpoint resume | `native-resume-comparison.json`: native resume invokes the later producer once; six exact Rewind replays invoke zero producers |

## Live and corpus evidence

- [Checkpointed live report](checkpointed-live.json): NVIDIA Nemotron Bolt and
  Gemini Flash Lite, 12 parent boundaries each, four callback completions and one
  native checkpoint per parent. Parent and fork each replay three times, with
  zero mutating producer calls in either fork.
- [Real corpus review](corpus-review.json): four 12-step recordings; 92 forward/
  backward positions rendered and checked against an independent state fold;
  interval comparisons use 100 queries per recording per candidate interval.
- [Perfetto parser report](perfetto-parser.json): 48 complete slices loaded
  unchanged, matching names/counts, with zero parser errors.
- [Long-run benchmark](snapshot-benchmark-final.json): 1,024 boundaries; default
  k=32 retains 32 checkpoints instead of 1,024 and applies at most 31 suffix
  events. Timings are executor observations, not universal performance claims.
- [Native resume comparison](native-resume-comparison.json) and
  [fork experiment report](fork-experiments.json).

## CI and reproducibility

The main test workflow runs the new regression tests on Python 3.11, 3.12 and
3.13, type/lint checks and package builds. The Month 3 acceptance workflow runs
checkpointed LangGraph examples, official Perfetto parsing, terminal navigation,
and real Jaeger collector/query/Chromium checks. Live requests are opt-in with
repository secrets and `REWIND_LIVE_VALIDATION=true`, or manual workflow dispatch;
missing credentials fail an explicitly requested live run. Skips are not live
proof. The committed two-provider live report comes from actual session runs.

No API keys, full live prompt/response recordings or terminal screenshots are
committed. Metadata reports are reproducible with the commands in
`docs/month3-time-travel.md`. The CAS/state additions preserve the frozen
boundary-log fields and old recordings; see ADR-0011.

## Defined scope

The planner asks for schema'd logical state, not a Python heap snapshot. Agents
must expose their state through captured boundaries or native checkpoint/callback
values. Native restoration requires declared state plus an explicit completed
node and matching frontier. Capture supports recorded async completion order;
fork execution remains serialized. Side-effect policy applies to mediated tools
in trusted Python code and is not an OS sandbox. These boundaries are documented
and tested; they are not silently presented as broader guarantees.
