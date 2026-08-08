# ADR-0006: Replay is playback of recorded outputs, not model re-execution

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma, @aasthaaa25, @kartikdua24

## Context

Rewind's core promise is that a recorded agent run can be replayed **bit-for-bit,
offline, with zero API calls**, and that the replay is *provably faithful*. There are
two mechanically different ways to "replay" an agent run, and they have opposite
properties:

- **Playback** — feed the agent the *recorded* LLM/tool output bytes at each boundary;
  the model is never re-invoked.
- **Re-execution** — actually call the model (and tools) again during replay.

The research pre-mortem (see [`../plan/risks-and-spikes.md`](../plan/risks-and-spikes.md))
established the decisive fact: LLM inference is nondeterministic even at temperature 0
(GPU floating-point non-associativity, dynamic batching, provider-side model drift where
the *same* model id changes behavior over time). Therefore any replay path that
re-invokes a model **cannot** be bit-exact without batch-invariant kernels the project
will not build. Conflating the two modes is the single most likely way to ship a
debugger that *silently lies* — the worst possible failure for a debugging tool.

Counterfactual **fork** ("what if this tool returned X?") is inherently a re-execution
past the fork point, so it cannot inherit the faithfulness guarantee.

## Decision

**We will make the core replay path pure playback, and treat re-execution as a
separate, explicitly-labeled mode.**

- Replay (`fr verify`, `fr show --at`, time-travel scrubbing) serves recorded boundary
  values and **never** re-invokes an LLM or tool. A **network kill-switch** is engaged
  during replay and raises on any outbound call not served from the recording.
- Faithfulness is verified, not assumed: every recording carries a boundary hash-chain
  (see [ADR-0008](0008-internal-recording-schema-otel-as-export.md) and
  [`../plan/algorithms-and-math.md`](../plan/algorithms-and-math.md) §1); replay
  recomputes it and **fails loud** at the first divergence.
- Counterfactual **fork** re-executes past the fork point and is presented as
  *best-effort exploration*, never as faithful reproduction. Mutating tools are mocked
  by default in fork mode.
- **Local models are never re-executed on the replay path** — their outputs are
  played back like any other boundary.

## Consequences

- **Easier:** the core guarantee becomes achievable and testable; LLM/GPU/provider
  nondeterminism is made *irrelevant* to replay faithfulness; the go/no-go spikes have a
  crisp pass/fail bar.
- **Easier:** replay is fast and free (no API cost, no GPU).
- **Harder / obligations:** the burden shifts entirely to **capture completeness** — we
  must intercept *every* nondeterministic boundary (clock, RNG, uuid, env, network, tool
  I/O, async completion order, global state), or replay diverges. This is now the
  project's top risk (R2/R3).
- **Constraint:** fork's usefulness is bounded — it explores hypotheses, it does not
  reproduce. The UI must make this distinction unmistakable (forked runs are
  quarantined).

## Alternatives Considered

- **Re-execute the model on replay (like LangGraph "time travel").** Rejected: not
  bit-exact — it re-rolls the dice, which defeats the entire purpose of a *debugger* and
  is exactly the incumbent behavior we differentiate against.
- **Re-execute only "cheap" local models.** Rejected: GPU inference is nondeterministic;
  Spike C measures this, and the result bans local-model re-execution from the replay
  path.
- **Offer one blended "replay" mode that sometimes re-executes.** Rejected: ambiguity
  here is how a debugging tool silently lies; the modes must be separate and labeled.
