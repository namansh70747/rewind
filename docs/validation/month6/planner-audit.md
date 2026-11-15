# Month 6 planner audit

Implementation scope: weeks 23–26 in the
[six-month roadmap](../../docs/roadmap.md#p5--lora-failure-explainer--hardening).
This branch stacks on Month 5. It does not merge that branch.

## Week-by-week evidence

| Week | Delivered on this branch | Status / Evidence |
|---|---|---|
| 23 | Concurrent replay (`month6.concurrent_replay`), performance benchmark (`scripts/validate_month6_performance.py`), structured `rewind.benchmark.v1` evidence record. | Passed. Replay throughput > 2,800 replays/s and boundary overhead < 15 us in `docs/release-evidence/performance-budget.json`. |
| 24 | Failing-agent demo, replay, bisect, fork recovery, newcomer walkthrough, `fr explain` and `fr gc` CLI commands. | Passed. Verified by `scripts/validate_month6_demo.py` and recorded in `docs/release-evidence/recovery-demo-qualification.json`. |
| 25 | LoRA cut documented in ADR-0014 and recorded in `lora_status` field of `rewind.explain.v1`. Replay safety and typing hardened. | Documented and accepted. Deterministic narration active; no ungrounded model hallucinations. |
| 26 | PR candidate on `feat/month-6-lora-explainer`. All 13 release gates pass `fr release-check`. Release guide and PyPI workflow configured. | Passed. Full release checklist verified in `docs/release-evidence/checklist.json`. |

## How to read the result

`explain()` is deterministic: it never calls a model. Every sentence comes from a
fixed template keyed on the classifier label. The `lora_status` field records the
explicit deferral decision from ADR-0014.

`retention_gc()` calls `store.garbage_collect()` after deleting run rows, so orphaned
blobs are always collected in the same transaction sweep.

All thirteen release gates in `docs/release-evidence/checklist.json` are attested
and digest-verified. `fr release-check` exits with status 0.

## Exit gates

| Gate | Status | Evidence Record |
|---|---|---|
| M6.1 `fr explain` returns deterministic narration from classifier label | Passed | `tests/test_month6.py` and `docs/release-evidence/recovery-demo-qualification.json` |
| M6.2 Concurrent replay completes N replays in parallel, all pass | Passed (>2,800 replays/s) | `docs/release-evidence/performance-budget.json` |
| M6.3 `fr gc --keep-last N` deletes older runs and collects orphan blobs | Passed | `tests/test_month6.py::test_retention_gc_keep_last_deletes_older_runs` |
| M6.4 LoRA deferral recorded in `lora_status` and ADR-0014 | Passed | `docs/adr/0014-month6-lora-explainer-stub.md` |
| M6.5 Performance budget approved on real workloads | Passed | `docs/release-evidence/performance-budget.json` |
| M6.6 Newcomer walkthrough validated end-to-end | Passed | `docs/release-evidence/recovery-demo-qualification.json` |
| M6.7 All release checklist gates attested and digest-verified | Passed (`checklist_complete: true`) | `docs/release-evidence/checklist.json` |
