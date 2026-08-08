# Team, Roles & Operating Cadence

Three engineers, six months. This doc defines **who owns what**, **the seams where they must collaborate**, **the weekly rhythm**, and **the Definition of Done** that gates every merge. It is tuned specifically for a 3-person team — light on ceremony, heavy on a shared end-to-end thread.

---

## The three roles

The project has exactly three workstreams, and they map cleanly to three owners. Assignments below are the **starting** allocation; swap by actual strength after the Month-1 spikes reveal where each person is fastest.

| Role | Owner | Owns | Hardest thing they carry |
|---|---|---|---|
| **E1 — Capture & Replay Core** | **@namansh70747 (Naman)** | Nondeterminism interception (LLM/embeddings, tool + MCP results, clock, RNG/seeds, env, retries, stream chunk order); the recording **log format**; the deterministic **playback** engine; the **divergence oracle** (hash-chain verify); the "code-changed-since-recording" detector; counterfactual **fork** engine + side-effect policy. | Making replay **provably bit-exact** — the entire product's credibility. This is the highest-risk role; it gets the most senior systems engineer. |
| **E2 — Developer Experience** | **@aasthaaa25** | The `fr` CLI (`record`/`replay`/`show`/`verify`/`fork`/`bisect`); the time-travel **timeline UI** (scrubbing, diff view, fork visualization); packaging & install; **framework integrations** (LangGraph adapter, OTel/OpenInference export & ingest); docs, examples, the killer demo. | The "does this feel good and is the demo undeniable" bar — rr only mattered because Pernosco's UI made it usable. |
| **E3 — ML / Data / Evaluation** | **@kartikdua24** | Failure **clustering** over recorded runs; the **eval harness** that uses replay+fork as deterministic, zero-cost fixtures; auto-**bisect** scoring/alignment logic; the (stretch) **LoRA failure-explainer**; the test corpus & metrics. | Everything ML depends on replay being deterministic — so this role is *blocked* until E1's core lands, and must stay useful in the meantime (build the corpus, heuristic baselines). |

> These are **owners, not silos.** Everyone reviews everyone; the person not on a given PR stays unblocked on their own thread.

### The load-bearing shared contracts

Integration hell in Month 4 comes from exactly three seams. They are frozen early (ADR) and changed only by ADR:

1. **The recording log format** — E1 owns it; E2 (reads it for every view) and E3 (reads it for ML/eval) both consume it. **Frozen ~Week 8.**
2. **The replay / fork / bisect API** — the functions E2 and E3 both call. Stabilized by Month 3.
3. **The OTel / OpenInference span mapping** — so recordings are also valid traces (interop + ingest). Co-designed E1↔E2.

### RACI on the load-bearing artifacts

| Artifact | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Log format & hash-chain | E1 | E1 | E2, E3 | all |
| Playback engine + divergence oracle | E1 | E1 | E2 | all |
| CLI + timeline UI | E2 | E2 | E1 | E3 |
| LangGraph / OTel adapters | E2 | E2 | E1 | E3 |
| Clustering + eval harness | E3 | E3 | E1, E2 | all |
| Test corpus & faithfulness metrics | E3 | E3 | E1 | all |
| ADRs (each) | proposer | the three | — | all |

---

## Effort estimates & the biggest schedule risks

Budget reality: 3 engineers × 26 weeks ≈ 78 gross e-weeks, but after ramp, meetings, and hardening plan for **~60–65 *productive* e-weeks**. The allocation below sums to the high end **on purpose** so scope-cutting is forced (LoRA/ML are the intended cut lines).

| Subsystem | Est. (e-weeks) | Priority | Schedule risk |
|---|---:|:--:|:--:|
| Capture layer (intercept every nondeterminism source) | 8–10 | P0 | **High** — completeness is everything |
| Deterministic playback + divergence oracle | 10–12 | P0 | **Highest** — the core moat; slip here last |
| Storage / log format (CAS blobs, index) | 4–5 | P0 | Medium (cheap if frozen early) |
| Time-travel + counterfactual fork | 5–6 | P0/P1 | Medium |
| Auto-bisect | 3–4 | P1 | Medium (thin over replay+verify) |
| Time-travel UI (CLI/TUI/Perfetto, then web) | 6–8 | P0 | Medium — it's the demo |
| MCP-fleet adapter | 4–5 | P1 | Med-High (protocol churn) |
| ML failure clustering | 4–5 | P1/P2 | Medium |
| LoRA explainer | 3–5 | P2 | **High (research)** — keep off critical path |
| Cross-cutting (OTel mapping, CI, packaging, docs) | 5–6 | P0 | Low-Med (always underestimated) |

**Top schedule risks, in order:** (1) deterministic playback + verification; (2) capture completeness; (3) MCP adapter (external churn); (4) LoRA (research). The Month-1 walking skeleton attacks (1) and (2) immediately; the log-format ADR de-risks the seams. Full risk register: [`risks-and-spikes.md`](./risks-and-spikes.md).

---

## Cadence (tuned for N=3)

- **Daily — async written standup** in a channel. No live daily meeting at three people; it's pure overhead. Flag blockers on the shared seams (log format / replay API) *immediately*, not at standup.
- **Weekly — one 60-minute live sync** = triage + **a live demo of the walking skeleton's current end-to-end thread**. Rotate who demos. Demo culture is the single best defense against integration drift.
- **Per iteration (2 weeks)** — scope review against the current monthly milestone, with an explicit, written **"what we are cutting"** decision (fixed-time / variable-scope). Iterations nest inside the six monthly milestones.
- **Monthly — milestone review** — check the gate in [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md); skim the ADR log; re-baseline scope down the ladder if needed.
- **Final ~3 weeks — cooldown/harden** — docs, examples, packaging, perf; ship the stretch (LoRA) only if the core is solid; **cut, don't slip**.

Why 2-week iterations (not Shape Up's 6-week cycles): a 3-person team can't afford to discover a bad bet five weeks in. Short loops + a fixed monthly gate.

---

## Definition of Done (enforced in CI)

A unit of work is **Done** only when it round-trips the core thread:

> **Recorded → replayed bit-exact (divergence oracle ✓) → visible on the timeline → covered by a test.**

Concretely, every merge to `main` must keep green:
- `ruff` + `ruff format --check` + `mypy` (already wired in CI).
- `pytest` including the **record → replay → `verify`** self-test with the **network kill-switch asserting zero outbound calls**.
- Snapshot tests (`syrupy`) for any changed recording/replay output.
- Docs/examples updated when user-facing behavior changes; an **ADR** added when a load-bearing decision changes; `CHANGELOG.md` updated.

Nothing is "done" because the code exists — it's done when it *round-trips and is proven faithful*.

---

## Tooling & conventions

- **GitHub Projects** — a single board. **Milestones = the six monthly milestones.** **Labels = the three workstreams** (`area:capture-replay`, `area:dx`, `area:ml`) plus `P0/P1/P2`, so ownership and priority are visible at a glance. Issues sized to close within one 2-week iteration.
- **ADRs** — one markdown file per significant decision in [`../adr/`](../adr/README.md), linked from the PR that implements it; reviewed at each milestone. The log-format and determinism ADRs are the ones that matter most.
- **Branches / PRs / commits** — see [`CONTRIBUTING.md`](https://github.com/namansh70747/rewind/blob/main/CONTRIBUTING.md): short-lived feature branches, Conventional Commits, every PR reviewed by at least one of the other two, the DoD gate enforced by CI.
- **CI from day one** — the walking-skeleton round-trip *is* the canary test; if it goes red, that's the top priority before any new feature.

---

*Starting role assignments are a hypothesis. Re-evaluate after the Month-1 spikes and reassign to wherever each engineer is demonstrably fastest — the roles are fixed, the names attached to them are not.*
