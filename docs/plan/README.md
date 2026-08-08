# Rewind — The 6-Month Build Plan

> This directory is the **operating plan** for building Rewind from an empty repo to a working, demoable, vendor-neutral flight recorder & time-travel debugger for AI agents — in six months, with three engineers, for **$0** in tooling.

It is written to be **precise and executable**: every month has a milestone gate, every week has per-person targets and an exit criterion, every hard part has a named open-source building block and the math behind it, and every serious risk has a mitigation and a *kill/pivot* criterion. It is grounded in deep research of the prior art (Mozilla `rr`, Pernosco, LangGraph, Temporal, DBOS, Langfuse, VCR.py, and 2025–26 academic work) — see [`competitive-landscape.md`](./competitive-landscape.md).

---

## The plan package (read in this order)

| Doc | What it gives you |
|---|---|
| **README.md** (this file) | North star, operating principles, the scope-cut ladder, the go/no-go gate |
| [`team-and-cadence.md`](./team-and-cadence.md) | The three roles, who owns what, the weekly rhythm, Definition of Done, tooling |
| [`roadmap-6-months.md`](./roadmap-6-months.md) | **The centerpiece** — all 26 weeks, per-person targets + exit criteria |
| [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md) | The 6 milestone gates, the final Definition of Done, the killer-demo script |
| [`risks-and-spikes.md`](./risks-and-spikes.md) | The pre-mortem risk register + the week-1–3 de-risking spikes |
| [`tech-stack-and-oss-map.md`](./tech-stack-and-oss-map.md) | The exact free/OSS library for every subsystem + licenses + gotchas |
| [`algorithms-and-math.md`](./algorithms-and-math.md) | The real math: hash-chains, boundary matching, alignment, checkpointing, HDBSCAN, LoRA |

---

## North Star — what "done" means at 6 months

> **A developer points Rewind at any Python AI agent, records a real run, and replays it bit-for-bit offline with the network unplugged and zero API calls — and Rewind proves the replay was faithful. When a run fails, they open the exact recording at the first decision that went wrong, ask "what if this tool had returned X?", and get an answer — without re-platforming onto anyone's framework.**

That is the GOAT bar, and it is deliberately singular: **faithful, vendor-neutral, zero-API replay of an agent run** is the thing no shipped tool does (observability tools only *view*; LangGraph's "time travel" *re-runs live*; durable-execution engines replay for *recovery*, not debugging). Everything else — fork, auto-bisect, ML clustering — is leverage *on top of* that core. See the honest competitive analysis in [`competitive-landscape.md`](./competitive-landscape.md).

The concrete end-of-6-months deliverable and demo script live in [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md).

---

## The one law everything obeys: **playback, not re-execution**

There are two ways to "replay," and conflating them is the fastest way to ship a tool that quietly lies:

- **Playback (the core promise).** Replay feeds the agent the *recorded* LLM/tool output bytes; the model is **never re-run**. This makes LLM/GPU/provider nondeterminism **irrelevant** to faithfulness — the problem shrinks to the agent *process* (clock, RNG, async order, globals) and to *capture completeness*. This must be bit-exact and verified.
- **Re-execution (fork only).** Counterfactual fork *must* re-invoke the model past the fork point, so it is inherently **best-effort exploration**, never advertised as faithful.

**Rule locked in Week 1:** the core replay path is pure playback with a network kill-switch; fork is a separate, clearly-labeled mode. This single decision reorders every risk — see [`risks-and-spikes.md`](./risks-and-spikes.md).

---

## Operating principles

1. **E2E-first — build a walking skeleton, not subsystems.** Month 1 produces one thin thread that runs end-to-end: record one real agent run → persist it → replay it bit-exact → see it on a timeline. Every later feature hangs off that thread, so the integration seams are exercised from week 2, not month 4.
2. **Working beats complete.** Correctness of the *core loop* is the priority; production hardening (scale, multi-tenant, security depth) is explicitly deferred. We are optimizing for "it works and it's provably faithful," not "it's production-grade."
3. **Fixed time, variable scope.** The six months are fixed. When we fall behind, we cut scope down the ladder below — we never slip the core.
4. **Spike before you commit.** The riskiest assumptions are tested with throwaway spikes in weeks 1–3, each with a pass/fail bar. A failed go/no-go spike triggers a documented pivot, not denial.
5. **Freeze the contracts early.** The recording **log format**, the **replay/fork/bisect API**, and the **OTel/OpenInference mapping** are the load-bearing seams between the three engineers. They are frozen via ADR by ~Week 8 and changed only by ADR after that.
6. **Faithfulness is a feature, not a hope.** Every recording carries a boundary **hash-chain**; replay recomputes it and **fails loud** on the first divergence. "Replay verified ✓/✗" is a first-class output. (Math in [`algorithms-and-math.md`](./algorithms-and-math.md) §1.)
7. **Don't reinvent; assemble.** Capture at the `httpx` transport layer; reuse OpenTelemetry/OpenInference for *presentation*; reuse Perfetto UI for the first waterfall; reuse Biopython/RapidFuzz/HDBSCAN for the algorithms. Our novelty is the *integrated whole*, not any single primitive.

---

## The scope-cut ladder (what we drop first if we fall behind)

Cut from the **bottom up**. The line above each cut must always ship.

```
MUST SHIP (the moat) ─────────────────────────────────────────────
  P0  Faithful record + playback + divergence oracle          ← never cut
  P0  Time-travel scrubbing (timeline UI)
  P0  Vendor-neutral capture (OpenAI + Anthropic via httpx)
───────────────────────────────────────────────────────────────────
  P1  Counterfactual fork (with side-effect safety)           ← cut #4
  P1  Auto-bisect (hash-chain first; alignment if time)       ← cut #3
  P1  MCP-fleet adapter + LangGraph adapter                   ← cut #3
───────────────────────────────────────────────────────────────────
  P2  ML failure clustering (embeddings + HDBSCAN)            ← cut #2
  P2  LoRA "failure-explainer" model                          ← cut #1 (first to go)
───────────────────────────────────────────────────────────────────
```

**Rationale (from the research):** any single pillar has prior art; ML clustering is our *weakest* differentiator and LoRA is a research bet with a cold-start data problem, so they are the cut lines. The defensible product is the P0 core plus as much P1 as time allows. Full reasoning in [`risks-and-spikes.md`](./risks-and-spikes.md) (R1, R9) and [`competitive-landscape.md`](./competitive-landscape.md).

---

## The go/no-go gate (end of Week 2)

Before we build anything real, two spikes decide whether the core thesis is even possible:

- **Spike A — bit-exact playback:** record a small OpenAI-backed agent, replay 50× in playback mode; **PASS = 50/50 byte-identical** with the divergence oracle never giving a false ✓.
- **Spike B — loud divergence:** inject un-captured nondeterminism (`time`, `random`, `uuid4`) and confirm replay **fails loudly** rather than diverging silently.

If A+B pass, we build. If they fail, we pivot per [`risks-and-spikes.md`](./risks-and-spikes.md) (down to "faithful recorder + trace viewer") rather than building fork/bisect/ML on sand. Full spike list (A–G) with pass/fail bars is in that doc.

---

## Success metrics (tracked weekly)

- **Faithfulness:** % of recorded runs in the test corpus that replay byte-identical (target: 100% on supported patterns; **any silent divergence is a P0 bug**).
- **Zero-API proof:** replay runs with the network kill-switch on, 0 outbound calls — asserted in CI.
- **E2E liveness:** the walking-skeleton round-trip (record→replay→verify→timeline) is green in CI every week from Week 4 onward.
- **Coverage:** number of nondeterminism sources interposed; number of agent frameworks/providers supported.
- **Demo readiness:** the "failing run → first diverging decision" demo runs on a real multi-tool/MCP agent by Month 5.

---

*This plan is a living document. Material changes go through an ADR in [`../adr/`](../adr/README.md) and are reflected here at the next milestone review.*
