# Competitive Landscape

*Part of the Rewind 6-month plan package. Siblings: [roadmap-6-months.md](./roadmap-6-months.md) · [risks-and-spikes.md](./risks-and-spikes.md) · [tech-stack-and-oss-map.md](./tech-stack-and-oss-map.md) · [README.md](./README.md)*

## Intro: the one lens that matters

**Rewind** is an open-source flight recorder and time-travel debugger for AI agents. It records the *nondeterministic inputs* of an agent run (LLM completions, tool I/O, retrieval results, clocks, random seeds) and then **replays that run bit-exact, offline, with zero API calls** — plus time-travel scrubbing, single-variable counterfactual fork, two-run auto-bisect, and ML failure clustering. The core is vendor-neutral, built on OpenTelemetry GenAI semantic conventions, with an MCP-fleet adapter.

There are dozens of tools in the "agent debugging / observability / eval" space, and it is easy to look at the list and conclude Rewind is a me-too. It is not — but the reason is subtle, and it collapses to a **single load-bearing distinction**:

> **RE-EXECUTE vs VIEW.** Does the tool *faithfully re-run a recorded run offline*, or does it only *display* what happened (and, when it claims to "replay," actually re-run something LIVE against a model/API)?

Rewind's **core law** is the difference between **playback** (bit-exact reconstruction of the exact past run, zero API) and **re-execution** (e.g. LangGraph re-runs nodes live and may return different results). Almost every product that markets "replay" or "time travel" for agents is doing live re-execution or pure viewing. Rewind lives in the **re-execute** column, but at the **agent-decision layer** — a place no shipped, vendor-neutral, laptop-first OSS tool currently occupies.

This document surveys five categories, scores each tool on the RE-EXECUTE-vs-VIEW axis, extracts what to steal, and is deliberately honest about where our differentiation is thin.

---

## Category 1 — Native record-replay / time-travel debuggers

*Rewind's true ancestors. These already deliver bit-exact re-execution + time-travel — but for native/browser processes, not agent decisions. The technique is ~15 years mature; our contribution is carrying it up to the agent-decision layer.*

- **Mozilla rr** — records *only* nondeterministic inputs (syscalls, signals, async events) using hardware performance counters, then replays deterministically under gdb with reverse execution. OSS permissive, ~10.6k stars, Linux-only, serializes execution to a single core. [github.com/rr-debugger/rr](https://github.com/rr-debugger/rr) · [rr-project.org](https://rr-project.org)
  - RE-EXECUTE. **Steal:** the founding principle — *record only the nondeterminism, everything else is deterministic glue*. For an agent, the LLM completion is the irreducible nondeterministic input, exactly analogous to a syscall return. Also steal rr's *chaos mode* for surfacing flaky bugs.
- **Pernosco** — commercial SaaS built on rr recordings; precomputes an *omniscient, queryable database* of the entire execution and offers dataflow-back-to-cause navigation. Proprietary, free tier. [pernos.co/about/vision](https://pernos.co/about/vision/)
  - RE-EXECUTE (+ precomputed analysis). **Steal:** the "why did this value become X?" UX → agent analog "why did the agent call tool Y here?", traced back to the prompt/context that caused it.
- **Undo / UDB LiveRecorder** — commercial time-travel debugging for C/C++/Go/Java/Rust on x86 + AArch64; "failing test / CI → drop into a TTD session at the point of failure," including recording from production. Proprietary. [undo.io/resources/live-recorder-production-software](https://undo.io/resources/live-recorder-production-software/)
  - RE-EXECUTE. **Steal:** the CI ergonomics — a failing pytest/CI run should *drop a `.rewind` bundle positioned at the point of failure*.
- **replay.io** — cloud, shareable time-travel debugging for the web; the DevTools frontend is OSS ([github.com/replayio/devtools](https://github.com/replayio/devtools)) but the recorder is proprietary. Pivoted in 2024, discontinued Test Suites and RIF. [replay.io](https://replay.io) · [replay.io/blog/a-new-direction](https://replay.io/blog/a-new-direction)
  - RE-EXECUTE. **Steal:** *recording-as-a-URL* — a bug report *is* a replayable artifact. **Cautionary tale:** even a technically excellent TTD company struggled to monetize a cloud recorder → an OSS, laptop-first wedge is the safer bet for us.
- **WinDbg TTD** — records *every instruction* of a Windows process; navigate like a video, set breakpoints in the past, and run LINQ-style queries over the whole trace. Proprietary, free. [learn.microsoft.com/.../time-travel-debugging-overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/time-travel-debugging-overview)
  - RE-EXECUTE (+ query). **Steal:** a **query language over the decision timeline** — "every tool error", "every retry", "first time context exceeded N tokens".
- **gdb record / reverse execution** — reverse-continue / reverse-step over an in-memory instruction log. GPL; ~200k-instruction cap, i386/amd64-linux only. [sourceware.org/gdb/.../Reverse-Execution.html](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Reverse-Execution.html)
  - RE-EXECUTE (bounded). **Steal:** reverse-step primitives, and the honest framing that *I/O is the hard part* of record-replay — the agent analog (tool I/O) is exactly what Rewind solves by recording it.

**Takeaway:** faithful record-replay + time-travel is a mature, ~15-year-old idea. Rewind is the first to carry it to the **agent-decision layer** in a vendor-neutral, laptop-first OSS package. We do not claim to invent record-replay.

---

## Category 2 — LLM / agent observability

*Critical honest finding: **this entire category is VIEW-only.** Their "playgrounds" re-run prompts LIVE against a provider. These are not re-execution competitors — they are capture and interop targets. Rewind should ingest their OTel output and position as "the thing that makes those traces runnable."*

- **Langfuse** — MIT core, ~21k stars, single-container self-host; tracing + prompt management + evals + datasets; OTel / LangChain / OpenAI integrations. Acquired by ClickHouse. [github.com/langfuse/langfuse](https://github.com/langfuse/langfuse)
  - VIEW. **Steal:** frictionless self-host UX; adopt their trace schema as an interop target.
- **LangSmith** — proprietary SaaS from the LangChain team; free 5k traces/mo, ~$39/seat, self-host is enterprise-only. [langchain.com/langsmith/observability](https://www.langchain.com/langsmith/observability)
  - VIEW. **Steal:** dataset-driven regression built from production traces. **Weakness for us:** it is the default incumbent for every LangChain shop.
- **Arize Phoenix** — Elastic License 2.0 (source-available, **not** OSI-approved), ~10.9k stars, OTel-native tracing + evals + datasets; its playground "replays" LLM calls **LIVE**. [github.com/Arize-ai/phoenix](https://github.com/Arize-ai/phoenix)
  - VIEW (playground re-runs live). **Steal:** OTel-first portable traces. **Note the license honestly:** ELv2 is not true OSS, which makes Rewind's Apache/MIT licensing a *real* differentiator here.
- **Helicone** — Apache-2.0 proxy/logger; one-line base-URL change; caching + cost tracking. Acquired by Mintlify (Mar 2026), now in maintenance mode. [github.com/Helicone/helicone](https://github.com/Helicone/helicone)
  - VIEW (+ proxy cache). **Steal:** proxy caching is a *primitive replay* for byte-identical requests — a useful capture fallback pattern.
- **Traceloop / OpenLLMetry** — Apache-2.0 OTel instrumentation for LLM providers and vector DBs. [github.com/traceloop/openllmetry](https://github.com/traceloop/openllmetry)
  - VIEW (capture). **Steal:** free, off-the-shelf capture instrumentation for Rewind to *consume*.
- **Langtrace** — app AGPL-3.0 / SDK Apache-2.0, ~1.2k stars, OTel, vendor-neutral. [github.com/Scale3-Labs/langtrace](https://github.com/Scale3-Labs/langtrace)
  - VIEW. **Steal:** their GenAI OTel semantic-convention work.
- **W&B Weave** — Apache-2.0 core; `@weave.op` auto-captures I/O / cost / latency; includes an eval framework. [docs.wandb.ai/weave](https://docs.wandb.ai/weave)
  - VIEW. **Steal:** one-decorator capture ergonomics.

**Takeaway:** complementary capture and interop targets, not re-execution competitors. Ingest their OTel output; do not rip-and-replace them.

---

## Category 3 — LLM eval / replay / regression

*Here "replay" means **re-run against a LIVE model to score the output** — not offline reconstruction. Every run costs API credits. Rewind's replayed runs should be invokable as deterministic, zero-cost eval fixtures.*

- **promptfoo** — MIT, ~23k stars; declarative CLI to compare / regress / red-team against live providers. [github.com/promptfoo/promptfoo](https://github.com/promptfoo/promptfoo)
  - RE-EXECUTE against LIVE model. **Steal:** declarative YAML test-matrix + CI ergonomics.
- **DeepEval** — Apache-2.0; 50+ metrics, pytest-style; Confident AI is the paid cloud. [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
  - RE-EXECUTE against LIVE model. **Steal:** pytest-native assertions → Rewind replays plug in as deterministic CI gates.
- **Braintrust** — proprietary; tracing + LLM-as-judge + playground + Brainstore; self-host is enterprise-only. [braintrust.dev](https://www.braintrust.dev)
  - RE-EXECUTE against LIVE model. **Steal:** the diff-two-runs UI and eval-first flow.
- **Ragas** — Apache-2.0, ~15.2k stars; RAG metrics + synthetic test-set generation. [github.com/explodinggradients/ragas](https://github.com/explodinggradients/ragas)
  - RE-EXECUTE against LIVE model. **Steal:** retrieval-specific metrics for the "retrieval" input Rewind records.
- **OpenAI Evals** — MIT, ~17.6k stars; framework + open registry; consumes credits. [github.com/openai/evals](https://github.com/openai/evals)
  - RE-EXECUTE against LIVE model. **Steal:** the idea of a **shared public registry** — reusable agent failure cases distributed as `.rewind` bundles.

**Takeaway:** evals answer "*is the output good?*" by calling the model again. Rewind answers "*what happened, and why did THIS run diverge?*" without calling anything. The clean integration: a Rewind replay *is* a deterministic, zero-cost eval fixture.

---

## Category 4 — Durable / replayable execution & agent state

*The **most dangerous category for our differentiation.** These systems already ship parts of replay, time-travel, and fork. Read this section skeptically and know exactly where we win and where we don't.*

- **LangGraph checkpointing + "time travel"** — OSS MIT; `get_state_history` lists checkpoints, you can replay from one, and `update_state` forks a branch. **Crucially, replay RE-EXECUTES NODES LIVE** — the docs state that "LLM calls, API requests, and interrupts fire again and may return different results." It is **not** bit-exact, and it is framework-locked. [docs.langchain.com/.../langgraph/use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
  - RE-EXECUTE **but LIVE, non-deterministic, framework-locked.** This is simultaneously the **closest prior art** to Rewind's fork *and* the **clearest place Rewind wins** — Rewind's fork is deterministic, zero-API, vendor-neutral, and perturbs a single variable.
- **Temporal** — OSS MIT; durable execution via event-history + deterministic replay; on restart it replays workflow code, skipping completed activities by restoring their recorded results; enforces determinism via a "replay test." [docs.temporal.io/workflow-execution](https://docs.temporal.io/workflow-execution)
  - RE-EXECUTE (for **crash recovery**). **Steal:** event-history-as-truth, and the **replay test** that flags when new code diverges from a recorded history (Rewind's auto-bisect is a cousin of this). **But:** replay exists for recovery, requires deterministic workflows, treats the LLM call as an opaque activity, and says nothing about *why* a decision changed.
- **DBOS** — MIT; Postgres-backed durable workflows; ships a **VS Code time-travel debugger** that replays past traces plus DB time-travel queries. [github.com/dbos-inc/dbos-transact-py](https://github.com/dbos-inc/dbos-transact-py) · [dbos.dev/blog/database-time-travel](https://www.dbos.dev/blog/database-time-travel)
  - RE-EXECUTE (durable-workflow steps + DB state). This is the tool that **most literally ships a "time-travel debugger"** — but for workflow steps and DB state, not agent decisions or counterfactuals. **Steal:** the literal replay-debugger UX and DB time travel.
- **Inngest** — SSPL → Apache (delayed license); durable step functions; "Replay" = bulk re-run of failed runs after a fix (recovery, live). [github.com/inngest/inngest](https://github.com/inngest/inngest)
  - RE-EXECUTE (LIVE, recovery). **Steal:** bulk-replay-a-fleet-after-a-fix as an operational pattern.
- **Restate** — source-available (BSL-style) core / permissive SDK, ~4.3k stars; journals every `ctx.run` step and replays completed steps from the journal on recovery. [github.com/restatedev/restate](https://github.com/restatedev/restate)
  - RE-EXECUTE (recovery). **Steal:** the per-step journal as a clean capture format.

**Takeaway (skeptical):** if you *build on* Temporal / DBOS / Restate / LangGraph you get a lot of replay machinery for free — which is exactly why this category is dangerous. Rewind's honest answer has three parts: **(a)** you should not have to adopt a durable-execution framework just to *debug* an agent; **(b)** their replay is for recovery/resumption and re-fires nondeterministic boundaries, whereas Rewind's is bit-exact and zero-API for debugging; **(c)** none of them models the **LLM decision as a first-class, replayable, forkable unit**, and none does **auto-bisect + counterfactual attribution**.

---

## Category 5 — HTTP cassette libraries

*Rewind's mechanistic ancestor. The pattern — "record nondeterministic I/O, replay offline with zero network" — is decades old. **Do not oversell it as novel.** Our novelty is the layer we apply it at, not the mechanism.*

- **VCR.py / vcrpy** — MIT; records HTTP to a YAML cassette and replays offline with zero network; configurable `match_on` and record modes (`once` / `new_episodes` / `none` / `all`). [github.com/kevin1024/vcrpy](https://github.com/kevin1024/vcrpy)
  - RE-EXECUTE (HTTP layer). **Steal:** the cassette format, match configuration, and record modes almost verbatim.
- **PollyJS** — Apache-2.0 (Netflix); record / replay / stub HTTP for Node + browser; HAR format; pluggable persister + adapter. [github.com/Netflix/pollyjs](https://github.com/Netflix/pollyjs)
  - RE-EXECUTE (HTTP layer). **Steal:** the adapter/persister plugin architecture and interchange format.
- **WireMock** — Apache-2.0, Java; mock server with record & playback, request matching, templating, and **fault / latency injection**. [wiremock.org](https://wiremock.org)
  - RE-EXECUTE (HTTP layer) + fault injection. **Steal:** fault/latency injection → power Rewind's counterfactuals: "what if this tool timed out / returned a 500 / returned malformed JSON?" as first-class perturbations.
- **mitmproxy** — MIT intercepting proxy; `mitmdump` for scripted capture; client- and server-side replay. [mitmproxy.org](https://mitmproxy.org)
  - RE-EXECUTE (HTTP layer). **Steal:** proxy-based **zero-instrumentation capture** as a fallback when you can't wrap the client.

**Takeaway:** "record nondeterministic I/O, replay offline with zero calls" is a solved problem at the HTTP layer. Rewind's novelty is **agent-decision granularity + OTel GenAI semantics + the fork/bisect/cluster layer on top**.

---

## The closest agent-space competitor to beat on marketing

**AgentOps** (OSS MIT, ~5.8k stars) explicitly markets "session replay" and "time-travel debugging" for agents. On inspection it is a **visual session viewer, not bit-exact re-execution.** [github.com/AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops)
- VIEW (despite the marketing). This is the name we most directly have to out-explain, because it uses our vocabulary for a VIEW-only product. Our demo has to make the RE-EXECUTE distinction visceral.

---

## Comparison table

| Tool | Category | OSS / license | Re-execute or View? | What to steal |
|---|---|---|---|---|
| Mozilla rr | 1 Native TTD | OSS, permissive | **Re-execute** (bit-exact, Linux) | Record only nondeterminism; chaos mode |
| Pernosco | 1 Native TTD | Proprietary (free tier) | **Re-execute** + precomputed queries | Dataflow "why did X happen?" UX |
| Undo / UDB LiveRecorder | 1 Native TTD | Proprietary | **Re-execute** | Failing test/CI → TTD bundle at failure |
| replay.io | 1 Native TTD | DevTools OSS; recorder proprietary | **Re-execute** | Recording-as-a-URL; monetization cautionary tale |
| WinDbg TTD | 1 Native TTD | Proprietary (free) | **Re-execute** + query | Query language over the timeline |
| gdb record/reverse | 1 Native TTD | GPL | **Re-execute** (bounded) | Reverse-step primitives |
| Langfuse | 2 Observability | MIT core | **View** | Frictionless self-host; trace schema |
| LangSmith | 2 Observability | Proprietary SaaS | **View** | Dataset-driven regression from prod traces |
| Arize Phoenix | 2 Observability | **ELv2 (source-available, not OSI)** | **View** (playground re-runs live) | OTel-first traces; our Apache/MIT is a real edge |
| Helicone | 2 Observability | Apache-2.0 | **View** + proxy cache | Proxy caching as primitive replay |
| Traceloop / OpenLLMetry | 2 Observability | Apache-2.0 | **View** (capture) | Off-the-shelf capture to consume |
| Langtrace | 2 Observability | AGPL-3.0 app / Apache-2.0 SDK | **View** | GenAI OTel semconv work |
| W&B Weave | 2 Observability | Apache-2.0 core | **View** | One-decorator capture ergonomics |
| promptfoo | 3 Eval/regression | MIT | **Re-execute vs LIVE model** | Declarative YAML matrix + CI |
| DeepEval | 3 Eval/regression | Apache-2.0 | **Re-execute vs LIVE model** | Pytest-native assertions |
| Braintrust | 3 Eval/regression | Proprietary | **Re-execute vs LIVE model** | Diff-two-runs UI; eval-first flow |
| Ragas | 3 Eval/regression | Apache-2.0 | **Re-execute vs LIVE model** | Retrieval-specific metrics |
| OpenAI Evals | 3 Eval/regression | MIT | **Re-execute vs LIVE model** | Shared public registry of failure cases |
| LangGraph time-travel | 4 Durable exec | MIT | **Re-execute — LIVE, non-deterministic, framework-locked** | Fork/branch API (we do it deterministically) |
| Temporal | 4 Durable exec | MIT | **Re-execute (recovery)** | Event-history-as-truth; replay test |
| DBOS | 4 Durable exec | MIT | **Re-execute (workflow + DB)** | Literal replay-debugger UX; DB time travel |
| Inngest | 4 Durable exec | SSPL → Apache (delayed) | **Re-execute (LIVE, recovery)** | Bulk-replay-a-fleet-after-a-fix |
| Restate | 4 Durable exec | Source-available core / permissive SDK | **Re-execute (recovery)** | Per-step journal as capture format |
| VCR.py / vcrpy | 5 HTTP cassette | MIT | **Re-execute (HTTP)** | Cassette format; match config; record modes |
| PollyJS | 5 HTTP cassette | Apache-2.0 | **Re-execute (HTTP)** | Adapter/persister plugin arch |
| WireMock | 5 HTTP cassette | Apache-2.0 | **Re-execute (HTTP) + fault injection** | Fault/latency injection → counterfactuals |
| mitmproxy | 5 HTTP cassette | MIT | **Re-execute (HTTP)** | Proxy-based zero-instrumentation capture |
| **AgentOps** | Agent-space | MIT | **View** (markets "time-travel" but is a viewer) | The marketing to out-explain |
| **Rewind** | **Agent-decision re-execution** | **Apache/MIT (planned)** | **Re-execute (bit-exact, zero-API, at decision layer)** | — |

---

## What to steal from each (concrete, implementable)

1. **rr — "record only nondeterminism":** treat the LLM completion as the single irreducible nondeterministic input (like a syscall return); everything else in the run is deterministic glue to be reconstructed, not recorded. Adopt chaos-mode-style perturbation for flaky-bug hunting.
2. **Pernosco — dataflow-to-cause:** ship a "why did the agent call tool Y here?" view that traces a decision back to the specific prompt/context tokens that caused it.
3. **Undo — failure-positioned bundles:** a failing pytest/CI run automatically emits a `.rewind` bundle already positioned at the first diverging decision.
4. **replay.io — recording-as-a-URL** (and its cautionary tale): make a bug report *be* a shareable replayable artifact; stay laptop-first/OSS to avoid the cloud-recorder monetization trap.
5. **WinDbg TTD — query language:** a small query DSL over the decision timeline ("every tool error", "every retry", "first time context exceeded N tokens").
6. **gdb — reverse-step primitives** and the honest framing that I/O is the hard part (which Rewind solves by recording tool I/O).
7. **Langfuse — frictionless self-host** and use its trace schema as an interop target.
8. **LangSmith — dataset-driven regression** assembled directly from production traces.
9. **Phoenix — OTel-first portable traces;** also use its ELv2 license as a contrast point for our permissive licensing.
10. **Helicone — proxy caching** as a primitive-replay capture fallback for byte-identical requests.
11. **Traceloop/OpenLLMetry — reuse their instrumentation** as a capture source Rewind consumes.
12. **Langtrace — GenAI OTel semconv work;** track and align with it.
13. **Weave — one-decorator capture** (`@weave.op`-style ergonomics) for zero-config recording.
14. **promptfoo — declarative YAML test-matrix + CI ergonomics** for the replay-as-regression suite.
15. **DeepEval — pytest-native assertions** so Rewind replays drop in as CI gates.
16. **Braintrust — diff-two-runs UI** as the visual anchor for auto-bisect output.
17. **Ragas — retrieval-specific metrics** applied to the "retrieval" input Rewind records.
18. **OpenAI Evals — a shared public registry** of reusable agent-failure cases distributed as `.rewind` bundles.
19. **LangGraph — the fork/branch API surface,** re-implemented deterministically (perturb one node, hold everything else bit-exact).
20. **Temporal — event-history-as-truth + the "replay test"** that flags divergence between new code and a recorded history (the seed of auto-bisect).
21. **DBOS — the literal VS Code replay-debugger UX** and DB time-travel queries.
22. **Inngest — bulk-replay-a-fleet-after-a-fix** as an operational workflow for MCP fleets.
23. **Restate — the per-step journal** as a clean, minimal capture format.
24. **VCR.py — cassette format, `match_on`, and record modes** (`once`/`new_episodes`/`none`/`all`).
25. **PollyJS — pluggable persister/adapter architecture** and a HAR-like interchange format.
26. **WireMock — fault/latency injection** as first-class counterfactuals ("what if this tool 500'd / timed out / returned malformed JSON?").
27. **mitmproxy — proxy-based zero-instrumentation capture** as a fallback when the client can't be wrapped.

---

## Why Rewind is genuinely novel vs all of these (and honest gaps)

### (a) Re-execution vs passive viewing — the real wedge (holds)

This is the differentiator that survives scrutiny. All of Category 2 and AgentOps are **VIEW-only**: their "playgrounds" and "replays" either re-run **LIVE** (Phoenix) or are **visual viewers** (AgentOps). Category 3 evals re-run **live and cost credits**. Rewind reconstructs the **exact past run offline, bit-exact, with zero API calls, at decision granularity** — something *no one* in Categories 2 or 3 offers.

**Honest bound:** the *mechanism* is old — VCR.py has done offline zero-network HTTP replay for a decade. So we do **not** claim to have invented record-replay. The defensible claim is narrower and true: **Rewind is the first to make an entire agent run bit-exact re-runnable, vendor-neutral, at the agent-decision layer on OTel GenAI semantics.**

### (b) Counterfactual fork + auto-bisect — no shipped agent tool does this (with a real caveat)

No shipped agent product ships single-variable counterfactual fork **or** two-run auto-bisect:
- **LangGraph's fork re-executes LIVE** — it re-samples everything downstream and is framework-locked. Rewind's fork perturbs **exactly one node** while everything else stays bit-exact — a **true controlled experiment** rather than a fresh, confounded re-run.
- **Auto-bisect** of a passing run vs a failing run down to the **first diverging decision** has **no productized equivalent** (git bisect is for commits; Temporal's replay test *detects* divergence but does not **localize** a decision-level root cause).

**Honest caveat — the academic prior art is real.** The underlying ideas appear in 2025–26 research:
- "Causal Agent Replay: Counterfactual Attribution for LLM-Agent Failures" — [arxiv.org/pdf/2606.08275](https://arxiv.org/pdf/2606.08275)
- **AGDebugger** — counterfactual message editing
- **DoVer** — intervention-driven auto-debugging — [arxiv.org/pdf/2512.06749](https://arxiv.org/pdf/2512.06749)
- Failure-attribution benchmarks — [arxiv.org/html/2604.22708v1](https://arxiv.org/html/2604.22708v1)
- Record-and-replay for agents — [arxiv.org/pdf/2505.17716](https://arxiv.org/pdf/2505.17716)

So the research validates the direction — but **no vendor-neutral, laptop-first OSS product ships faithful replay + fork + bisect together.** Our novelty is the **productized integration**, not any isolated primitive.

### (c) Vendor-neutral vs framework-locked — real, but partly contested

The OTel-GenAI-native core works across frameworks and providers, whereas LangGraph time-travel only works if you *are* LangGraph, and Temporal / DBOS / Restate only work if you adopt their runtime. The genuine advantage: **you should not have to re-platform onto a workflow engine just to debug an agent.**

**Honest about incumbents:**
- DBOS **literally ships a "time-travel debugger."**
- Temporal / Restate / Inngest all do deterministic replay (for recovery).
- rr / Pernosco / Undo / WinDbg TTD nailed bit-exact re-execution + scrubbing **15 years ago**.
- VCR.py / PollyJS / WireMock / mitmproxy do offline zero-network replay.
- **Fleet failure clustering already exists** in Arize, PostHog, and Langfuse — so **ML clustering is our weakest differentiator and should not lead the pitch.**

The defensible claim is **the combination at the agent-decision layer**: faithful zero-API replay **+** single-variable counterfactual fork **+** two-run auto-bisect **+** a vendor-neutral OTel core, in one OSS laptop-first tool. **Any single pillar has prior art; the assembled whole, at this granularity and vendor-neutral, does not exist.**

---

## Positioning / adoption

**Primary user.** An engineer building a **non-trivial multi-tool agent — especially an MCP fleet — who is drowning in nondeterministic, un-reproducible failures and is not willing to re-platform onto Temporal / DBOS / LangGraph just to debug.** Today they use Langfuse / LangSmith / Phoenix to **stare at traces** and promptfoo / DeepEval to **re-run and hope** — and still cannot answer "*why did THIS run fail when yesterday's succeeded?*"

**Why they'd switch or adopt-alongside:**
- **vs observability (Cat 2):** "You can *view*; Rewind *re-runs* the exact run offline, bit-exact, free, and lets you *fork* it." Consume their OTel output — don't rip-and-replace.
- **vs LangGraph (Cat 4):** framework-neutral, and the fork is a **real controlled experiment**, not a live re-sample.
- **vs Temporal / DBOS (Cat 4):** no durable runtime to adopt; replay is for **debugging decisions**, not crash recovery.
- **vs evals (Cat 3):** your regression suite becomes **deterministic and zero-cost** — a replayed run *is* a fixture.

**The wedge (killer demo):** *"failing run → open the exact `.rewind` bundle positioned at the first diverging decision."* Bit-exact replay + a real auto-bisect, on a laptop, with zero API calls.

**The honest risk.** The category is crowded and incumbents own every adjacent piece. **Our moat is only the integrated whole, executed cleanly end-to-end.** If the demo does not show **bit-exact replay + a real auto-bisect that no incumbent can reproduce**, the differentiation will read as incremental. Everything depends on a working E2E demo, not a feature list.

**One structural caveat.** OpenTelemetry's GenAI/agent conventions are still **"Development" (not Stable)** as of July 2026, and were split into a dedicated repo in June 2026 ([john-hodge.com/blog/opentelemetry-genai-semantic-conventions](https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/)). "Vendor-neutral on OTel GenAI" means **building on a moving target — plan for schema churn.**

---

## How this informs the roadmap

- **Lead with the wedge, not the feature list.** The E2E-first roadmap must land the "failing run → `.rewind` bundle at the first diverging decision" demo early — it is the *only* thing that makes the RE-EXECUTE distinction visceral against a VIEW-only field. See [roadmap-6-months.md](./roadmap-6-months.md).
- **Buy, don't build, the mechanism.** Reuse cassette-layer patterns (VCR.py record modes, PollyJS persister arch, WireMock fault injection, mitmproxy fallback capture) rather than reinventing record-replay. See [tech-stack-and-oss-map.md](./tech-stack-and-oss-map.md).
- **Interop over replacement.** Consume OTel output from Cat 2 tools and expose replays as Cat 3 eval fixtures; position Rewind as the layer that makes existing traces *runnable*, not a competitor to observability.
- **De-risk the OTel dependency.** Schema churn in the GenAI conventions is a first-class risk — pin versions, isolate the mapping layer, and track the dedicated repo. See [risks-and-spikes.md](./risks-and-spikes.md).
- **Don't lead with clustering.** ML failure clustering is the weakest differentiator (prior art in Arize/PostHog/Langfuse) — ship it as a later-phase nicety, never as the headline.
- **Prove fork + bisect against LangGraph directly.** The sharpest contrast is a side-by-side: LangGraph re-samples downstream on fork; Rewind perturbs one node and holds the rest bit-exact. That comparison belongs in the demo and the docs.
