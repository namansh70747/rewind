# Month 1 status — Foundations & Go/No-Go (Weeks 1–4)

**Status: COMPLETE (M0 + M1 gates met in CI / mam console)**  
Evidence date: 2026-09-10 · Demo: `demos/week2_mam/` · Plan refs: [`roadmap-6-months.md`](./roadmap-6-months.md), [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md)

> How to read: this is the **execution status** for Month 1 against the frozen plan. The week-by-week roadmap text stays the source of intent; this file records what shipped and how it is proven.

---

## Gate M0 — Go/No-Go

| # | Criterion | Status | Evidence |
|---|---|---|---|
| M0.1 | Spike A bit-exact playback | PASS | `month1_proof._spike_a` / mam Spikes tab / `verify` N/N |
| M0.2 | Spike B loud divergence | PASS | Tamper oracle localizes to boundary #2; Session clock/uuid/rng shims |
| M0.3 | Spikes C–F written verdicts | PASS | C policy (ADR-0006); D concurrent fail-loud; E refactor survival; F redaction recall |
| M0.4 | Go / pivot ADR | PASS | [`docs/adr/0006-replay-is-playback-not-re-execution.md`](../adr/0006-replay-is-playback-not-re-execution.md) |

---

## Gate M1 — Walking Skeleton

| # | Criterion | Status | Evidence |
|---|---|---|---|
| M1.1 | `fr record -- python agent.py` | PASS | `flightrecorder.runner` + CLI extras; `tests/test_week2_mam_demo.py::test_fr_record_unmodified_script` |
| M1.2 | `fr verify` bit-exact, kill-switch | PASS | Walking-skeleton + mam verify 100× |
| M1.3 | `fr show` timeline | PASS | CLI Rich table + mam Good/Failed timeline |
| M1.4 | CI canary record→replay→verify | PASS | `tests/test_walking_skeleton.py`, mam demo tests |

---

## Week map (plan → shipped)

| Week | Theme | Shipped |
|---|---|---|
| 1 | Spike A bit-exact | Capture + hash-chain verify N/N |
| 2 | Spikes / go-no-go | Tamper + ADR-0006; spikes pack in UI |
| 3 | Capture + store | SQLite WAL + CAS dedup; `@fr.tool`; `fr record -- python` |
| 4 | Playback + verify (M1) | Kill-switch verify; corpus faithfulness %; mam console |

---

## Demo

```powershell
.\demos\week2_mam\run.ps1
```

Open http://127.0.0.1:8765/ — **Live agent**, gate cards, spikes, corpus, good/failed, bisect, verify 100×.

Live agent: real Open-Meteo geocode/weather; LLM uses `NVIDIA_API_KEY` when set, else stub.
