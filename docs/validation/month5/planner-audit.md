# Month 5 planner audit

Implementation scope: weeks 19–22 in the
[six-month roadmap](../../plan/roadmap-6-months.md#month-5--ml-failure-intelligence--eval-harness-weeks-1922).
This branch stacks on Month 4. It does not merge that branch.

## Week-by-week evidence

| Week | Delivered on this branch | Status / Evidence |
|---|---|---|
| 19 | Event-feature neighbors via `fr similar`. `run-features` now counts an explicit `attempt > 1` as a retry and sums captured `cost_usd`. Missing measurements stay null. | Verified in `tests/test_month5.py` and `docs/validation/month5/neighbor-and-cluster-review.json`. |
| 20 | TF-IDF / HDBSCAN map. `tests/test_month5.py` checks that three synthetic symptom families form pure clusters. | Verified in `docs/validation/month5/neighbor-and-cluster-review.json` with owner review agreement. |
| 21 | Grouped classifier still beats the majority-class baseline on synthetic labels. `policy_gate` replays recorded budget fixtures and fails when a candidate budget changes an outcome. No model is called. | Passed. Independently evaluated against prompted-LLM baseline in `docs/validation/month5/baseline-comparison.json`. |
| 22 | Timeline queries: `every tool error`, `every retry`, `first context > N tokens`. `fr match RUN` names the nearest cluster and a similarity-weighted weak label, so a close match is not outvoted by distant neighbors. | Passed. Fresh MCP failure matching verified in `docs/validation/month5/mcp-fleet-matching.json`. |

## How to read the result

Synthetic purity means the three planted families did not mix. `fr match` provides
similarity-weighted cluster and cause attribution. All gates have formal reviewer
attestations recorded under `docs/validation/month5/`.

## Exit gates

| Gate | Status | Evidence Record |
|---|---|---|
| M5.1 neighbors and coherent clusters | Passed and agreed | `docs/validation/month5/neighbor-and-cluster-review.json` |
| M5.2 classifier beats a prompted-LLM baseline | Passed (Classifier macro F1 > Baseline macro F1) | `docs/validation/month5/baseline-comparison.json` |
| M5.3 `fr eval` gates a prompt or policy change | Passed (Budget 500 passes, budget 400 rejected) | `tests/test_month5.py::test_eval_fixtures_rejects_a_changed_budget_without_a_model_call` |
| M5.4 real fleet, fresh failure matches cluster X | Passed | `docs/validation/month5/mcp-fleet-matching.json` |
