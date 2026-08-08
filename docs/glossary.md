# Glossary

Precise definitions of the core terms used throughout the Rewind documentation. For
how they fit together, see [Architecture](architecture.md).

---

### Boundary

The seam between the agent's own deterministic code and the outside world. Every
nondeterministic value an agent reads — an LLM completion, a tool result, the clock, a
random number, an environment variable, an HTTP response — crosses a boundary. Rewind
mediates every boundary with one uniform interceptor. The agent's own deterministic
computation is *not* a boundary and is never captured.

### Boundary Log

The append-only, totally-ordered record of every value that crossed a boundary during
a run. It is the **spine** of Rewind: replay, scrubbing, forking, and bisection are
all operations over the Boundary Log. Its authoritative index (the ordinal boundary
keys) lives in SQLite; the payload bytes live content-addressed in the blob store.

### Cassette / record-replay

**Record-replay** is the technique of capturing a program's nondeterministic inputs
once ("recording") and later feeding them back so the program re-runs identically
("replay") — the principle behind Mozilla `rr` and, for HTTP, VCR-style test tools. A
**cassette** is the informal name for a single stored recording (Rewind's persisted
Boundary Log plus its blobs) that can be replayed. Rewind applies this idea to whole
agent runs, not just to native programs or single HTTP calls.

### Passive playback

Replay mode (`PLAYBACK`) that reads the Boundary Log to render and scrub the timeline
**without running any agent code**. Used by the UI. Contrast with re-execution replay.

### Re-execution replay

Replay mode (`REEXEC_REPLAY`) that re-runs the **agent's own code**, serving recorded
values back at each boundary and **never calling the real world**. This is what proves
a run is reproducible (`fr verify`) and what a fork is built on. The two "replays" —
passive playback and re-execution replay — are deliberately distinct: one runs no
agent code, the other re-runs all of it.

### Fork / counterfactual

A **counterfactual fork** answers "what if this boundary had returned X?" Rewind
replays to step N under re-execution, **injects the mutation** X, then switches to a
**live continuation** from N onward. The result is saved as a separate, **quarantined**
run. Because live continuation can re-trigger real side effects, mutating tools are
governed by the side-effect policy.

### Bisect

Auto-bisect takes a **passing** run and a **failing** run and finds the **first
diverging decision** between them. It sequence-aligns the two runs (Needleman–Wunsch /
DTW with a semantic cost), distinguishes *same-input → different-output* (the decision
diverged) from *different-input → different-output* (walk back further), and classifies
the divergence. Named by analogy to `git bisect`.

### Divergence class

The category assigned to a divergence found during bisection (or a mismatch found
during replay). The taxonomy includes: **arg-hallucination**, **tool-choice**,
**sampling-flake**, **tool-result-drift**, **retrieval-drift**, **loop**,
**cost-blowup**, **truncation**, and **api-error**. A divergence class serves double
duty: it is a human-readable root cause *and* a weak label for the ML layer.

### Network kill-switch

The **seatbelt**. During re-execution replay, any outbound call that is **not** served
from the recording **raises immediately** instead of silently reaching the network.
This converts the most dangerous failure mode — silent unfaithful replay, where a
plausible-but-wrong value is served without anyone noticing — into a loud, located
error at the exact unmatched boundary.

### OpenTelemetry GenAI conventions

The [OpenTelemetry](https://opentelemetry.io/) semantic conventions for generative-AI
workloads. Rewind uses them as its **structural and index layer**: a standard,
vendor-neutral description of a run's causal structure (spans) that can be viewed for
free in Jaeger, Tempo, or Perfetto. Because OTel content capture is opt-in and
truncated, Rewind does **not** rely on it for payloads — it stores the real payload
bytes itself, content-addressed.

### Side-effect policy

The rules that keep forks and live continuations safe. The **side-effect policy
engine** classifies every tool as **read-only** or **mutating** (default: mutating),
**mocks** mutating tools by default in fork mode, offers a **human-gate** for explicit
approval, and supports a **per-tool sandbox hook** (e.g. `urunc`) for cases where a
mutating tool must genuinely run in isolation.
