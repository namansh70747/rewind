# FAQ

Short, accurate answers to the questions people ask first. For the full picture see
[Design](design.md) and [Architecture](architecture.md).

---

### Isn't this just Langfuse / LangSmith / Arize Phoenix?

No. Those are excellent **passive trace viewers** — they ingest spans and let you
*view* what an agent did. None of them can **re-execute** a run. Rewind's whole point
is active re-execution: it captures every boundary read with enough fidelity to serve
those values back and run the agent's own code again, deterministically and offline.
That unlocks things a viewer fundamentally cannot do — verifying a run replays
identically, scrubbing through reconstructed state, forking a run to ask "what if?",
and bisecting a passing run against a failing one. They answer "what happened?";
Rewind answers "run it again and let me change one thing." Rewind also exports standard
OpenTelemetry spans, so it complements rather than replaces your existing viewer.

### Why is deterministic replay hard?

Because an agent reads nondeterminism from many places at once — LLM sampling, tool
I/O, wall-clock time, RNG and UUIDs, hash seeding, env/config, retrieval, generic
HTTP, and async completion order. Miss *any* one of them and replay silently drifts.
Rewind captures all of them through one uniform interceptor. It then has to serve them
back in the **right order**, which is why boundary matching is ordinal-primary
(thread, type, call-site, **occurrence number**) so loops and retries don't collide,
and content-validated so mismatches surface as divergences instead of being served
silently. Finally, the **network kill-switch** enforces the whole thing: any outbound
call not served from the recording raises, turning silent-unfaithful-replay — the #1
credibility risk for a record-replay tool — into a loud, located error.

### Does replay cost API money?

No. Re-execution replay makes **zero external calls**. The LLM is never queried, no
tool actually runs, and the clock is frozen to its recorded value — every boundary
read is served from the recording. The network kill-switch guarantees this: if
anything tried to reach the real world during replay, it would raise rather than spend
money or cause a side effect. (Passive playback, used for scrubbing the timeline, runs
no agent code at all, so it obviously costs nothing either.) The one exception is a
**fork's live continuation**, which by design runs for real *after* the mutation point —
and even then, mutating tools are mocked by default under the side-effect policy.

### What if the agent's code changes after a recording?

Replay re-runs the agent's *own* code, so code drift is a real concern and Rewind
handles it explicitly. Every recording stores a **code fingerprint**, and replay
offers three modes: **strict** (refuse to replay if the fingerprint differs),
**lenient** (replay but flag the drift), and **live-fallback** (allow live calls where
the code has moved, for controlled cases). This makes drift a visible, deliberate
decision rather than a silent source of wrong results.

### Is it tied to one framework?

No. The core is **vendor-neutral**, built on the OpenTelemetry GenAI conventions and
interception via `wrapt` wrappers, decorators, and determinism shims — so unmodified
OpenAI, Anthropic, and LangGraph agents can be recorded and replayed. On top of that
neutral core, Rewind ships a **first-class adapter** for the author's own MCP tool
fleet as the proving ground for the fleet/ML features. See
[ADR-0002](adr/0002-vendor-neutral-otel-core-plus-fleet-adapter.md).

### What does it cost to build and run?

The entire stack is **free and open-source**: Python 3.11+, `uv`, `wrapt`,
`opentelemetry-sdk`, `sqlite3` + `zstandard` + `duckdb` + `pyarrow` + `lancedb`, Typer
+ Rich for the CLI, FastAPI + React for the web timeline, scikit-learn +
sentence-transformers + hdbscan + umap-learn for the ML layer, Ollama for a local LLM,
and pytest for tests. Storage is **embedded and local-first** — SQLite plus a
content-addressed `zstd` blob store (deduplicated across runs), DuckDB, and LanceDB —
so there is **no server to run** and no hosted database to pay for. Even the ML
training data is free: it comes from bisect divergence classes, heuristic labeling
functions, a local Ollama LLM-as-judge, and synthetic failures manufactured by the
fork. Rewind is Apache-2.0 licensed.
