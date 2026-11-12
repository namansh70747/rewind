# Month 3 validation closeout

The full [planner audit](planner-audit.md) now maps every week 10–13 requirement
and M3.1–M3.4 gate to implementation and evidence. It supersedes the earlier
partial implementation reports.

| Check | Result |
| --- | --- |
| Regression suite | 137 tests passed |
| Static/package checks | Ruff lint/format, strict mypy, wheel/sdist and strict docs build passed |
| Live NVIDIA + Gemini | Both checkpointed LangGraph parents and safe live forks completed |
| Exact offline replays | 12 across the four new recordings |
| Mutating fork producer calls | 0 |
| Native callbacks/checkpoints | Four callback completions and final native checkpoint per parent |
| Real corpus terminal review | Four 12-step recordings; 92 inspected forward/back positions |
| Perfetto parser | Four unchanged files, 48 slices, zero parser errors |
| Long-run reconstruction | 1,024 boundaries; default interval 32; suffix bounded to 31 |
| Native checkpoint resume comparison | Native later producer runs once; Rewind replays/fork invoke no producers |
| CAS/schema compatibility | Incremental manifests, bounded ancestry, source binding, GC/reopen, legacy reads tested |
| CLI tool policy | Default simulation and per-tool live manifest authorization tested |
| Controlled experiments | Fresh fixtures and verified, optionally persisted quarantined children |
| OTel viewer | Jaeger ingestion, queried spans and browser checks in acceptance workflow |

Current evidence: [checkpointed live](checkpointed-live.json),
[corpus review](corpus-review.json), [Perfetto](perfetto-parser.json),
[long-run benchmark](snapshot-benchmark-final.json),
[native resume](native-resume-comparison.json),
[experiments](fork-experiments.json).

Earlier evidence remains available in `live-provider-gate.json`, per-provider
live reports and the original snapshot benchmark. The current checkpointed
example includes more boundaries than the earlier seven-step state-stream-only
example. Keys were used only in the session and were never committed. CI's live
requests are explicitly opt-in; the normal PR gate requires no provider secrets.

The exact behavioral scope, cold/warm complexity and serialization compatibility
are defined in [ADR-0011](../../adr/0011-month3-logical-state-and-checkpoints.md)
and the workflow guide. The PR remains unmerged.
