# ADR-0001: Flagship — a deterministic record-replay + time-travel debugger

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma (@namansh70747)

## Context

AI agents are nondeterministic across many axes at once — LLM sampling, tool and
external I/O, wall-clock time, RNG/UUID/hash seeding, retrieval, and async completion
order. As a direct consequence, **production agent failures cannot be reproduced**:
re-running an agent produces a *different* run and the original failure disappears.

The existing market — Langfuse, LangSmith, Arize Phoenix — consists of **passive trace
viewers**. They record spans and let you *view* what happened, but none can
**re-execute** a run. This is exactly the gap Mozilla's `rr` closed for ordinary
programs and that nobody has closed for agents.

We need to decide what the flagship capability of this project is. The decision is
load-bearing: it dictates the entire architecture (capture fidelity, replay engine,
storage), so it must be made first. Several genuinely different products could be built
on top of "instrument an agent," and we can only build one flagship well.

## Decision

**We will build Rewind as a deterministic record-replay and time-travel debugger for
AI agents.**

The core thesis is that an agent run is a pure function of the nondeterministic values
it reads at its boundaries: `outcome = agent_code(sequence_of_boundary_reads)`. We
capture every boundary read once (RECORD) and re-execute the agent's own code against
that recording with zero external calls (REEXEC_REPLAY). From this single capability
we derive faithful offline replay, time-travel scrubbing, counterfactual forks,
auto-bisect, and — later — ML failure intelligence.

Faithfulness is treated as the first-class credibility requirement: replay matching is
ordinal-primary and content-validated, and a **network kill-switch** turns any
unmatched outbound call into a loud, located error rather than a silent wrong result.

## Consequences

**Easier**

- We can *reproduce* a specific production failure offline and interrogate it, not just
  view it — a capability no competitor offers.
- Time-travel, forks, and bisect all fall out of the same recording, so one hard
  investment (faithful capture + replay) yields five features.
- The clear thesis gives the roadmap a spine: every phase ships a working E2E slice of
  the same idea.

**Harder / costs**

- Faithful replay is genuinely difficult: we must intercept *every* boundary and match
  values correctly under loops, retries, and concurrency, or replay drifts.
- We take on the credibility risk of silent-unfaithful-replay, which forces us to build
  the network kill-switch and divergence surfacing from the start.
- We must handle non-idempotent side effects for forks (deferred to the side-effect
  policy engine), which a pure viewer never has to think about.

## Alternatives Considered

- **An agent security firewall (taint-tracking + sandbox).** Intercept agent I/O to
  detect and block dangerous actions (prompt injection, exfiltration) via taint
  tracking and sandboxing. Rejected as the flagship: it is a policy/enforcement product
  whose value is prevention, not reproducibility, and it does not close the
  "can't reproduce the failure" gap that is the sharpest unmet need. (Sandboxing does
  reappear, narrowly, as the per-tool sandbox hook in the side-effect policy.)

- **A regression-CI / deterministic-simulation harness.** Freeze recorded runs as
  golden tests and re-run them in CI to catch regressions. Rejected as the flagship
  because it is a *downstream application* of record-replay, not the primitive: without
  faithful capture and re-execution it cannot exist, and once we have those, a CI
  harness is a thin layer we can add later rather than the product's core.
