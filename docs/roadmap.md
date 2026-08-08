# Roadmap

> 📌 **A detailed, data-driven 6-month execution plan will be added here next — this
> page currently captures the phase structure.** (The owner will add the 6-month plan
> in a follow-up.)

Rewind is built in six phases, **P0 through P5**. Each phase is defined by a single
rule: it ends with a **working end-to-end capability**, expressed as a concrete
"Done when" milestone. No phase is considered complete on the strength of internal
scaffolding alone — there must be a demonstrable capability a user can run.

The architecture behind each of these capabilities is described in
[Architecture](architecture.md).

---

## P0 — Walking skeleton

The minimal record → replay → CLI loop, end to end. This phase proves the core thesis
(that a run is a pure function of its boundary reads) on the smallest possible surface.

- Record a run into a **Boundary Log**.
- Re-execute it under `REEXEC_REPLAY`.
- A `fr` CLI to drive and inspect it.

**Done when** `fr verify <run>` proves an **identical replay with zero API calls**, and
`fr show <run>` prints the run's timeline.

---

## P1 — Faithful recorder + local web timeline

Harden the recorder to real agents and add a browser timeline for scrubbing.

- Streaming capture, multi-provider support, OTLP export.
- The **network kill-switch** (the seatbelt) enforcing faithful replay.
- PII redaction on export.
- A browser-based timeline UI.

**Done when** any **unmodified OpenAI / Anthropic / LangGraph agent** records, scrubs,
and **replays deterministically**.

---

## P2 — Time-travel + counterfactual fork

Add state reconstruction and the ability to change history safely.

- State reconstruction via replay-to-N plus periodic snapshots.
- Mutate a recorded value and continue **live**.
- The **side-effect policy engine** so dangerous tools don't fire on a fork.

**Done when** you can **scrub to step N, change a tool result, and replay forward with
dangerous tools mocked**.

---

## P3 — Auto-bisect

Turn two runs into a root cause.

- Sequence alignment (Needleman–Wunsch / DTW) with a semantic cost.
- Semantic diff and divergence **classification** into the taxonomy.
- A side-by-side comparison UI.

**Done when** it **pinpoints the first diverging decision between a passing and a
failing run**.

---

## P4 — Fleet adapter + ML failure intelligence

Scale from one run to a whole fleet.

- Instrument the author's **672-tool / 10-provider** fleet.
- The ML pipeline: features → embeddings → LanceDB → classifier + clustering.
- A failure-intelligence dashboard.

**Done when** it **clusters and root-causes failures across hundreds of real runs**.

---

## P5 — LoRA failure-explainer + hardening

Narrate root cause in plain English and make the system production-grade.

- Fine-tune a small local model (LoRA) to explain a run's root cause.
- Concurrent replay.
- Retention / garbage collection and run sharing.

**Done when** you can **paste a failing run and get a plain-English root cause plus a
suggested fix**.

---

## Phase summary

| Phase | Theme | Done when |
| --- | --- | --- |
| **P0** | Walking skeleton | `fr verify` proves identical replay with zero API calls; `fr show` prints the timeline. |
| **P1** | Faithful recorder + web timeline | Any unmodified OpenAI/Anthropic/LangGraph agent records, scrubs, and replays deterministically. |
| **P2** | Time-travel + counterfactual fork | Scrub to step N, change a tool result, replay forward with dangerous tools mocked. |
| **P3** | Auto-bisect | Pinpoints the first diverging decision between a passing and a failing run. |
| **P4** | Fleet + ML intelligence | Clusters and root-causes failures across hundreds of real runs. |
| **P5** | LoRA explainer + hardening | Paste a failing run, get a plain-English root cause and fix. |
