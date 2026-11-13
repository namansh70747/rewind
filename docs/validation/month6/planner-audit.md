# Month 6 planner audit

Implementation scope: weeks 23–26 in the
[six-month roadmap](../../docs/roadmap.md#p5--lora-failure-explainer--hardening).
This branch stacks on Month 5. It does not merge that branch.

## Week-by-week evidence

| Week | Delivered on this branch | Still open |
|---|---|---|
| 23 | Concurrent replay (`month6.concurrent_replay`), synthetic benchmark (`month6.benchmark_replay`), structured `rewind.benchmark.v1` evidence record. | Production throughput on real hardware with the author's fleet cassettes. |
| 24 | Demo replay confirmed inside `test_month6.py` via `_make_simple_run` fixture. `fr explain` and `fr gc` CLI commands added to `commands.py`. | Real failing-agent demo and documentation site publication. |
| 25 | LoRA cut documented in ADR-0014 and recorded in `lora_status` field of `rewind.explain.v1`.  Replay safety and typing are hardened. | No model-training claim; the deferral decision is recorded for maintainer review. |
| 26 | PR candidate on `feat/month-6-lora-explainer`. CHANGELOG entry. CI workflow updated to include Month 5 and Month 6 target branches. Month 6 acceptance workflow added. | Code Owner review, CI tag, and final real-data Definition of Done. |

## How to read the result

`explain()` is deterministic: it never calls a model.  Every sentence comes from a
fixed template keyed on the classifier label.  The `lora_status` field records the
explicit deferral decision from ADR-0014.

`retention_gc()` calls `store.garbage_collect()` after deleting run rows, so orphaned
blobs are always collected in the same transaction sweep.

`concurrent_replay()` uses `concurrent.futures.ThreadPoolExecutor` and returns a
`ConcurrentReplayResult` with `passed`, `failed`, `elapsed_s`, and
`throughput_replays_per_s`.

## Exit gates

| Gate | Status |
|---|---|
| M6.1 `fr explain` returns deterministic narration from classifier label | Passes on synthetic corpus. Human review of real labels is open. |
| M6.2 Concurrent replay completes N replays in parallel, all pass | Passes on the synthetic single-boundary cassette. Real fleet timing is open. |
| M6.3 `fr gc --keep-last N` deletes older runs and collects orphan blobs | Passes on SQLite fixture. Production GC sweep timing is open. |
| M6.4 LoRA deferral recorded in `lora_status` and ADR-0014 | Done. Training remains deferred pending a reviewed labeled corpus. |
