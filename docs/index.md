# Rewind

**A flight recorder and time-travel debugger for AI agents.**

> Record-replay (à la Mozilla `rr`) meets `git bisect` — Sentry/Datadog for AI-agent debugging.

Rewind records everything an AI agent reads from the outside world, then re-runs the
agent's own code against those recorded values to reproduce a run **exactly**, with
**zero external calls**. From that one capability you get faithful offline replay,
time-travel scrubbing, counterfactual "what if?" forks, automatic bisection of a
passing run against a failing one, and fleet-wide ML failure clustering.

- **Import package:** `flightrecorder`
- **CLI:** `fr`
- **License:** Apache-2.0
- **Author:** Naman Sharma ([@namansh70747](https://github.com/namansh70747))
- **Status:** design complete, pre-alpha — not yet implemented

---

## The problem in one paragraph

AI agents are nondeterministic. They depend on LLM sampling, tool I/O, wall-clock
time, RNG, and external APIs, so a production failure cannot be reproduced by simply
running the agent again. When a deployed agent makes a wrong tool call, hallucinates
an argument, blows up token cost, or loops forever, the engineer has no way to
re-run the *exact* failure. Existing tools — Langfuse, LangSmith, Arize Phoenix — are
**passive trace viewers**: they show you what happened but cannot re-execute it. This
is precisely the gap Mozilla's `rr` closed for ordinary programs; nobody has closed
it for agents.

## The solution in one sentence

Treat an agent run as a pure function of the nondeterministic values it read —
`outcome = agent_code(sequence_of_boundary_reads)` — capture every boundary read once,
then feed the recording back in to re-execute the run deterministically.

## Where to go next

| Page | What it covers |
| --- | --- |
| [Design](design.md) | The vision, the pure-function insight, the five features, and why Rewind is novel and defensible. |
| [Architecture](architecture.md) | The Boundary Log spine, the four modes, capture, replay, the network kill-switch, time-travel, fork, auto-bisect, storage, and the ML layer. |
| [Roadmap](roadmap.md) | The six phases (P0–P5), each with a concrete "Done when" milestone. |
| [Glossary](glossary.md) | Precise definitions of the core terms used throughout the docs. |
| [FAQ](faq.md) | Straight answers to the common questions ("isn't this just Langfuse?", "does replay cost API money?"). |
| [Architecture Decision Records](adr/README.md) | The accepted decisions behind the design, in MADR format. |
