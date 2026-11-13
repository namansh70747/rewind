# Month 5 planner audit

Implementation scope: weeks 19–22 in the
[six-month roadmap](../../plan/roadmap-6-months.md#month-5--ml-failure-intelligence--eval-harness-weeks-1922).
This branch stacks on Month 4. It does not merge that branch.

## Week-by-week evidence

| Week | Delivered on this branch | Still open |
|---|---|---|
| 19 | Event-feature neighbors via `fr similar`. `run-features` now counts an explicit `attempt > 1` as a retry and sums captured `cost_usd`. Missing measurements stay null. | A human review of neighbor quality on a real corpus. Optional BGE/LanceDB search still needs a local model directory. |
| 20 | TF-IDF / HDBSCAN map. `tests/test_month5.py` checks that three synthetic symptom families form pure clusters. | Human agreement that clusters are coherent on real runs. Ollama narration stays on the existing local-model command. |
| 21 | Grouped classifier still beats the majority-class baseline on synthetic labels. `policy_gate` replays recorded budget fixtures and fails when a candidate budget changes an outcome. No model is called. | A prompted-LLM baseline collected before the held-out labels were visible. `fr compare-baseline` is the command for that file. |
| 22 | Timeline queries: `every tool error`, `every retry`, `first context > N tokens`. `fr match RUN` names the nearest cluster and a similarity-weighted weak label, so a close match is not outvoted by distant neighbors. | The author's 672-tool / 10-provider fleet and hundreds of real runs. |

## How to read the result

Synthetic purity means the three planted families did not mix. It does not mean a
production failure has been root-caused. `fr match` says that in its
`qualification` field.

## Exit gates

| Gate | Status |
|---|---|
| M5.1 neighbors and coherent clusters | Software path passes on the synthetic corpus. Human review on real runs is open. |
| M5.2 classifier beats a prompted-LLM baseline | Open. Majority-class comparison passes; the prompted baseline is not measured. |
| M5.3 `fr eval` gates a prompt or policy change | Recorded-budget replay gate passes for budget 500 and fails for budget 400. |
| M5.4 real fleet, fresh failure matches cluster X | Open. `fr match` works on supplied local recordings only. |
