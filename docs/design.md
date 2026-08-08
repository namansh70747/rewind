# Design

This page is the vision-and-design narrative for Rewind: the problem it exists to
solve, the single insight the whole system is built on, the five features that fall
out of that insight, and why Rewind is meaningfully different from the trace viewers
that already exist.

For the *how* — the components, modes, and data model — see [Architecture](architecture.md).

---

## The problem: production agent failures cannot be reproduced

An AI agent is one of the most nondeterministic programs you can deploy. On a single
run its behaviour depends on:

- **LLM sampling** — temperature, top-p, and seed mean the same prompt can yield a
  different completion each time.
- **Tool and external I/O** — the results of API calls, database reads, retrieval,
  and web requests change from moment to moment.
- **Wall-clock time** — `now()`, timeouts, and date logic all read a moving target.
- **RNG and identifiers** — `random`, `uuid4`, `os.urandom`, and hash seeding.
- **Concurrency** — the order in which async tasks complete.
- **Human and external inputs** — anything a person or upstream system feeds in.

Because of this, when a deployed agent misbehaves you cannot simply run it again to
study the failure. Re-running produces a *different* run, and the bug you were chasing
evaporates.

### A concrete failure: the invoice agent

Consider a billing agent with two tools: `preview_invoice` (read-only, safe) and
`send_invoice` (mutating, charges a customer). In production, on one particular run,
the model hallucinates and calls `send_invoice` when it should have called
`preview_invoice`. A customer is charged in error. This is exactly the kind of
incident an engineer must root-cause.

But when they try to reproduce it:

1. They re-run the agent with the "same" input.
2. The LLM samples a different token path; the tool results have changed; the clock
   has moved.
3. This time the agent calls `preview_invoice` correctly. **The failure is gone.**

The engineer is left staring at a passive trace of the bad run with no way to
interrogate it. Was it a sampling flake? A hallucinated argument? A drifted tool
result upstream? A retrieval miss? With a passive viewer, you can only guess.

## The insight: an agent run is a pure function of its boundary reads

Strip away the nondeterminism and an agent run is deterministic. All the randomness
enters at the *boundary* between the agent's own code and the outside world — every
LLM completion, tool result, clock read, random number, and env lookup. If you record
the exact sequence of values that crossed that boundary, then re-running the agent's
own code while feeding those recorded values back in will reproduce the run **exactly**:

```
outcome = agent_code(sequence_of_boundary_reads)
```

The agent's own deterministic computation (its control flow, prompt assembly, parsing)
is *not* recorded — it is simply re-executed. Only the boundary reads are captured.
Replay makes **zero external calls**: the LLM is never queried, no tool actually runs,
the clock is frozen to what it was. This is the same principle that makes Mozilla's
`rr` work for native programs; Rewind applies it to agents.

## Five features fall out of one recording

Once you have a faithful recording of every boundary read, five capabilities follow
directly from it:

| # | Feature | What it does | Why the recording enables it |
| --- | --- | --- | --- |
| 1 | **Faithful offline replay** | Re-execute the exact run with zero API calls. | Recorded values are served back to the agent's code in order. |
| 2 | **Time-travel scrubbing** | Step, rewind, and fast-forward through a run's timeline. | The log is a totally-ordered sequence you can render at any point. |
| 3 | **Counterfactual fork** | "What if this tool had returned X?" — mutate a value and run forward live. | Replay to the mutation point, inject X, then switch to live continuation. |
| 4 | **Auto-bisect** | Given a passing and a failing run, pinpoint the first diverging decision. | Two comparable recordings can be sequence-aligned and diffed. |
| 5 | **ML failure intelligence** | Cluster and root-cause failures across a whole fleet. | Every recording becomes a feature vector plus text for embeddings. |

For the invoice agent, this means: you replay the exact bad run offline and watch the
model choose `send_invoice`; you scrub to that decision; you fork it — "what if the
context had contained the 'draft only' flag?" — and watch the corrected behaviour with
the dangerous `send_invoice` tool **mocked** so no real charge occurs; and you bisect
the bad run against a known-good one to get a one-line answer: *the tool-choice
diverged at step 7 on identical input, so this was a sampling flake — pin the seed or
lower the temperature.*

## Why this is novel and defensible

Every existing agent-observability product — **Langfuse, LangSmith, Arize Phoenix** —
is a **passive trace viewer**. It ingests spans and lets you *view* what happened.
None of them can **re-execute** a run, because none of them capture the full set of
boundary reads with the fidelity required to serve them back deterministically. They
answer "what did the agent do?" Rewind answers "**run it again and let me change
one thing.**"

That gap is defensible because closing it is genuinely hard and cuts across the whole
stack:

- **Fidelity** — you must intercept every boundary uniformly (LLM, tools, clock, RNG,
  network, async order) or replay silently drifts. Rewind's answer is one uniform
  interceptor plus a **network kill-switch** that turns silent-unfaithful-replay (the
  single biggest credibility risk) into a loud, located error.
- **Correctness under loops and retries** — boundary matching is ordinal-primary
  (thread, type, call-site, occurrence number) and content-validated, so loops and
  retries replay in the right order instead of colliding.
- **Safety of forks** — re-executing forward can re-trigger non-idempotent side
  effects (re-send an email, re-charge a card). A **side-effect policy engine**
  classifies every tool and mocks mutating ones by default in fork mode.

None of these are features you can bolt onto a trace viewer after the fact; they
require designing the capture and replay engine around them from day one.

## Who needs this

- **Agent engineers** debugging a specific production failure they cannot otherwise
  reproduce.
- **Platform and reliability teams** who need a Sentry/Datadog-style workflow —
  capture, replay, root-cause — for agents in production.
- **Teams running large tool/provider fleets** who need to cluster hundreds of
  failures and find the common root cause instead of triaging one at a time.
- **Anyone building safety-sensitive agents** who needs to ask counterfactual
  "what if?" questions without re-triggering real-world side effects.

Continue to the [Architecture](architecture.md) for the full technical design, or see
the [Roadmap](roadmap.md) for how it gets built.
