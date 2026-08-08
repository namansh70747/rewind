# Milestones, Gates & Definition of Done

Six monthly **gates**, each a hard go/no-go. A gate is either met (all its criteria green in CI) or it isn't — "almost" means re-baseline scope down the [scope-cut ladder](./README.md#the-scope-cut-ladder-what-we-drop-first-if-we-fall-behind), not slip the core. The week-level detail lives in [`roadmap-6-months.md`](./roadmap-6-months.md); the risks each gate retires are in [`risks-and-spikes.md`](./risks-and-spikes.md).

---

## Gate M0 — Go/No-Go (end of Week 2) 🚦

The project's foundational bet, tested before real building.

| # | Exit criterion | Evidence |
|---|---|---|
| M0.1 | **Bit-exact playback** (Spike A) | 50/50 replays of a real OpenAI agent are byte-identical; divergence oracle gives no false ✓ |
| M0.2 | **Loud divergence** (Spike B) | Injected un-captured `time`/`random`/`uuid4` cause replay to **fail and localize**, never diverge silently |
| M0.3 | Spikes C–F have written verdicts | Local-model determinism measured; concurrency, refactor-survival, redaction, and footprint assessed |
| M0.4 | A **go / pivot decision** is recorded as an ADR | If M0.1/M0.2 fail → pivot to "faithful recorder + trace viewer" and re-baseline |

**If this gate fails, stop and pivot.** Do not build fork/bisect/ML on an unfaithful core.

---

## Gate M1 — Walking Skeleton (end of Week 4)

| # | Exit criterion |
|---|---|
| M1.1 | `fr record -- python agent.py` produces a persisted recording for a real single-tool agent |
| M1.2 | `fr verify <run>` **replays it bit-exact with the network kill-switch on — zero outbound calls** |
| M1.3 | `fr show <run>` renders the decision timeline |
| M1.4 | The record→replay→verify round-trip is the CI **canary test** and is green |

*Retires:* R2/R3 (silent divergence) at toy scale. The end-to-end thread now exists.

---

## Gate M2 — Faithful Recorder & Verification (end of Week 9)

| # | Exit criterion |
|---|---|
| M2.1 | Any **unmodified OpenAI *and* Anthropic** agent records → replays bit-exact → verifies |
| M2.2 | **Streaming (SSE)** tool-calling runs replay byte-identical (reassembled) |
| M2.3 | Loops/retries replay recorded failures **in order** (`occurrence_index`) |
| M2.4 | 🔒 **Log format frozen via ADR**; content-addressed storage dedups; recordings export/import & still verify |
| M2.5 | **Redaction pre-storage**: 0 secrets in the stored corpus; boundary-coverage audit is clean |

*Retires:* R4 (partially), R6, R13; freezes the #1 integration seam.

---

## Gate M3 — Time-Travel & Counterfactual Fork (end of Week 13)

| # | Exit criterion |
|---|---|
| M3.1 | Scrub to **any step N** of a long run and inspect exact reconstructed state (replay-to-N + snapshots) |
| M3.2 | Time-travel UI v1: Textual scrubber **and** Perfetto trace export |
| M3.3 | **Counterfactual fork**: change a tool result at step N, replay forward with **mutating tools mocked by default**; no real side effect fires; fork saved as a quarantined run |
| M3.4 | A **LangGraph** agent records/replays/forks; a recording opens unchanged in an OTel viewer |

*Retires:* R10 (fork side-effects); establishes interop and the demo surface.

---

## Gate M4 — Auto-Bisect & Fleet Capture (end of Week 18)

| # | Exit criterion |
|---|---|
| M4.1 | Given a **passing and a failing** run of the same task, `fr bisect` pinpoints the **first diverging decision** (hash-chain for aligned; alignment for insert/delete) |
| M4.2 | The divergence is **named** in plain English (taxonomy) with the raw diff shown; a human agrees on a real pair |
| M4.3 | An agent driving **multiple MCP servers** records & replays bit-exact via the adapter |
| M4.4 | Concurrent-tool (`asyncio.gather`) agents replay within the documented sequential/concurrent guarantee |

*Retires:* R5, R14, R17; delivers the second headline capability.

---

## Gate M5 — ML Failure Intelligence & Eval (end of Week 22) — *P1/P2, cuttable*

| # | Exit criterion |
|---|---|
| M5.1 | Failure **clustering** (embeddings + HDBSCAN) is coherent on the corpus; `fr similar` returns sensible neighbors |
| M5.2 | Root-cause classifier (weak-supervision labels) **beats a prompted-LLM baseline** on held-out labels |
| M5.3 | `fr eval` runs replays as **deterministic zero-cost fixtures** and gates a prompt/model change |
| M5.4 | Dogfooded on the **real 672-tool MCP fleet**: a fresh failure surfaces "matches cluster X + likely cause" |

*Retires:* R9 (as far as feasible). **If behind, cut per the ladder** — M5 is not allowed to endanger the M1–M4 core.

---

## Gate M6 — Cooldown & Release (end of Week 26) — final

| # | Exit criterion |
|---|---|
| M6.1 | `pip install rewind && fr --help` works on a clean machine; `v0.1.0` tagged with CHANGELOG/release notes |
| M6.2 | Capture overhead measured & acceptable (recorder doesn't perturb the agent) |
| M6.3 | The **killer demo** is reproducible from the docs by a newcomer |
| M6.4 | Either a working **LoRA failure-explainer** *or* a documented decision to cut it plus a hardened core |
| M6.5 | The **final Definition of Done** (below) is met |

---

## The final Definition of Done (end of 6 months)

Rewind `v0.1.0` ships when **all** of these are true:

1. **Faithful, vendor-neutral, zero-API replay.** A developer records any unmodified OpenAI/Anthropic (and LangGraph, and MCP-fleet) Python agent and replays it **bit-for-bit offline with the network unplugged**, and Rewind **proves** the replay was faithful (divergence oracle ✓).
2. **Time-travel.** They scrub the decision timeline and inspect exact state at any step, in the terminal and in Perfetto.
3. **Counterfactual fork.** They ask "what if this tool returned X?" and get an answer, with dangerous tools mocked by default — clearly labeled best-effort, never conflated with faithful replay.
4. **Auto-bisect.** Given a passing and a failing run, Rewind names the first diverging decision.
5. **Interop.** Recordings are valid OTel/OpenInference traces; existing traces can be ingested.
6. **Installable & documented.** `pip install rewind`, a docs site, a quickstart, worked examples, and a public gallery of `.rewind` bundles.
7. *(Stretch, cuttable)* ML failure clustering on a real fleet and/or a LoRA failure-explainer.

Items **1–4 are the moat and are non-negotiable**; 5–6 make it usable; 7 is upside. This is the GOAT bar from [`README.md`](./README.md).

---

## The killer-demo script (the thing we show the world)

> 1. Run a real multi-tool agent (ideally on the MCP fleet). It fails on one run — a wrong tool call.
> 2. `fr verify <run>` — replay it **offline, network unplugged, zero API calls**. It reproduces the failure *exactly*. (Contrast: LangGraph "time travel" re-rolls the dice.)
> 3. `fr bisect <good> <bad>` — Rewind jumps to the **first diverging decision** and names the cause ("given the same context, the agent chose `send_invoice` instead of `preview_invoice`").
> 4. `fr fork <run> --at N` — change that tool's recorded result; replay forward (mutating tools mocked). The agent **recovers**.
> 5. `fr similar <run>` — "this failure matches 7 others in cluster *arg-hallucination*."

If steps 2 and 3 land on a real agent that no incumbent can reproduce, the differentiation is undeniable. That is the whole game.

---

## KPIs tracked to each gate

| KPI | Target |
|---|---|
| Faithfulness (corpus replays byte-identical) | 100% on supported patterns; **any silent divergence = P0 bug** |
| Zero-API proof | 0 outbound calls on replay, asserted in CI |
| E2E canary (record→replay→verify→timeline) | green every week from W4 |
| Nondeterminism sources interposed | grows to full coverage by M2 |
| Providers / frameworks supported | OpenAI + Anthropic (M2), LangGraph (M3), MCP fleet (M4) |
| Bisect accuracy on labeled pairs | first-divergence correct ≥ target on the corpus |
| Secrets leaked to storage | **0** |
