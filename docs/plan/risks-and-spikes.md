# Rewind — Risks & Spikes

> Part of the 6-month plan package. See the [plan index](./README.md) · [team & cadence](./team-and-cadence.md) · [tech stack & OSS map](./tech-stack-and-oss-map.md) · [algorithms & math](./algorithms-and-math.md) · [competitive landscape](./competitive-landscape.md) · [6-month roadmap](./roadmap-6-months.md) · [milestones & exit criteria](./milestones-and-exit-criteria.md).

**Rewind** is an open-source flight recorder and time-travel debugger for AI agents (Python; package `flightrecorder`, CLI `fr`; repo [github.com/namansh70747/rewind](https://github.com/namansh70747/rewind)). It records the nondeterministic inputs of an agent run and replays them **bit-exact, offline, with zero API calls**; on top of that it adds time-travel scrubbing, counterfactual fork, auto-bisect, and ML failure clustering.

This document is the honest ledger of what can go wrong, what could make the whole thing *impossible*, and the cheap experiments we run in Weeks 1–3 to find out before we build on sand. It is written for a 3-person team over 6 months with an explicit posture of **"work end-to-end first, not production-hardened."**

The single most important idea in this document is the reframing in the next section. Read it first: it reorders every risk that follows.

---

## The reframing that reorders every risk: playback vs re-execution

There are two fundamentally different things a "replay" can mean, and conflating them is the most likely way this project ships something that quietly lies.

### (A) Playback — the core promise

On replay, Rewind **feeds back the recorded output bytes** at each nondeterministic boundary. The LLM is *never re-invoked*. The tool call is *never re-issued*. The clock is *never read live*. Everything the agent process consumed from the outside world is served from the recording.

The consequence is liberating: **LLM, GPU, provider, and temperature nondeterminism become irrelevant to replay faithfulness.** It does not matter that GPU floating-point is non-associative, that dynamic batching reshuffles kernels, that a provider silently swapped model weights, or that `temperature=0` is not actually deterministic in practice — because we never re-run the model. We replay the *bytes it produced that one time.*

Under playback, the problem collapses to a much smaller and more tractable one: **determinism of the agent process itself, plus completeness of capture.** Concretely, that means async/task scheduling, RNG, the clock, `dict`/`set` ordering under hash randomization, module globals and import-time singletons, and whether we interposed on *every* boundary through which nondeterminism can enter. That is a hard problem, but it is a *finite, enumerable* problem — and it is the problem we are choosing to solve.

### (B) Re-execution — the tempting trap

The moment replay **re-invokes the model** — which is exactly what you need for counterfactual fork ("what if the agent had chosen differently here?"), and exactly what is tempting for locally-hosted models where "just run it again" feels free — **all of the LLM nondeterminism comes flooding back**. Bit-exactness becomes unattainable without batch-invariant kernels, and those cost on the order of ~60% of throughput to obtain ([Thinking Machines — Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)).

### The decision we lock in Week 1

- **Core replay = pure playback.** Bit-exact, zero-API, offline. This is the promise we make and verify.
- **Fork = best-effort exploration only.** It re-executes, so it can never be called "faithful." It is a thinking tool, not a source of truth.

We will treat this distinction as a **core law of the codebase**, enforced in naming, in the API surface, and in the UI. A user must never be able to mistake a re-executed fork for a faithful replay. **Conflating playback and re-execution is the single most likely way Rewind ships something that quietly lies — and a debugger that lies is worse than no debugger.**

---

## Risk register

Ordered by likelihood × severity (highest first). Likelihood/Severity scale: **L** (low), **M** (medium), **H** (high), with **M-H** between. Every row carries an explicit **KILL/PIVOT** criterion — a pre-committed decision about what we do if the risk materializes. These criteria are the point of this document: they let us change course early instead of sinking months into a doomed approach.

| ID | Risk | Likelihood | Severity | Early-warning signal | Mitigation | KILL / PIVOT criterion |
|----|------|:---:|:---:|------|------|------|
| **R2** | **Silent divergence from incomplete capture.** Record-replay is all-or-nothing: miss one source — `time()`, `random`/`uuid4`, `os.urandom`, env vars, `dict`/`set` order under hash randomization, filesystem, retries with jitter — and replay diverges catastrophically. ([ACM Queue — Engineering Record/Replay](https://queue.acm.org/detail.cfm?id=3391621)) | H | H | On a fixed corpus, replays diverge with no *identifiable* missing source. | Interpose at **every** boundary; freeze `PYTHONHASHSEED`; seed all RNGs; enumerate boundaries exhaustively. | If a fixed corpus still shows > *X%* divergent replays with **no identifiable missing source** → pivot to **bounded-scope replay** (LLM + tool boundary only). |
| **R3** | **No faithfulness oracle.** We cannot *prove* a replay is faithful. A debugger that silently lies is worse than none. | H | H | Divergence detector produces false ✓ in testing. | Build a **divergence detector**: hash the full input to every boundary during replay, compare to the recording, **HARD-FAIL LOUD on the first mismatch**. Make "replay verified ✓/✗" a first-class, visible result. | If the detector cannot be made reliable (false ✓s persist) → **reposition Rewind as a trace viewer**, not a faithful replayer. |
| **R4** | **Boundary-matching breaks under code drift / refactor.** Recordings keyed to call-site, order, or args become invalid after a refactor: last week's recording won't replay against today's code. | H | H | Recordings fail to replay after routine refactors in dogfooding. | Key by **semantic boundary identity** (logical step id + content hash), not source line; pin recording to git SHA and **warn on mismatch**; provide a rematch/migrate tool. | If recordings cannot survive routine refactors → **per-commit replay only**, no cross-version replay (this kills "debug last month's incident against current code"). |
| **R5** | **Async / thread / parallel scheduling divergence.** Parallel tool calls and `asyncio` interleave differently on each replay; `rr`'s answer is to serialize onto one core. ([ACM Queue — Engineering Record/Replay](https://queue.acm.org/detail.cfm?id=3391621)) | H | H | Concurrent-agent replays match inconsistently across runs. | Match concurrent boundaries by **content / causal key**, not arrival order; record happens-before order; optionally force a single-threaded model boundary. | If concurrent agents cannot replay faithfully → **scope the guarantee to sequential agents**. |
| **R1** | **Scope over-ambition.** 3 people / 6 months for record + replay + scrub + fork + bisect + ML + LoRA + OTel core + MCP adapter — *any one of these is a project.* | H | H | End of **Month 2**: replay is not byte-stable on a toy agent. | **Ruthless MVP** = deterministic record + playback + scrub *only*; fork/bisect/ML are Phase 2. | If by end of **Month 3** replay is not bit-exact on ≥1 real framework → cut fork + bisect + ML and ship a faithful **recorder**. |
| **R6** | **PII / secrets capture + redaction correctness.** A flight recorder captures *everything*; OTel content capture is opt-in precisely because prompts and tool args carry PII and credentials. One leaked recording is a security incident — for a *debugging* tool. ([Uptrace — OTel for AI systems](https://uptrace.dev/blog/opentelemetry-ai-systems); [OneUptime — Redacting sensitive prompts](https://oneuptime.com/blog/post/2026-02-06-redact-sensitive-prompts-genai-opentelemetry-traces/view)) | M-H | H | Secret-scan of a stored recording finds an unredacted secret. | **Redact before storage** (never capture-then-scrub); redaction **on by default**; **deny-by-default** content capture; encrypt at rest; secret-scan the recording as a test. | If redaction cannot be made high-recall → **content capture off by default** (this guts fidelity — a conscious trade). |
| **R10** | **Counterfactual fork non-idempotent side effects.** A live continuation can re-send email or re-charge a card; LangGraph docs warn that resume re-fires LLM/API calls. ([LangGraph — Time travel](https://langchain-ai.github.io/langgraph/concepts/time-travel/)) | M | H | A forked run re-executes a side-effecting tool in testing. | **Default fork to dry-run/playback** for side-effecting tools; per-tool opt-in to go live; classify tool idempotency; sandbox. | If effect-classification cannot be made safe → **fork runs in replay-only mode** (no live re-execution). |
| **R11** | **Competitive obsolescence.** LangGraph already ships checkpoint / time-travel / replay / fork. ([LangChain — Use time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)) | M | H | A framework ships faithful cross-version replay + bisect before we do. | Compete on **vendor-neutral + bit-exact + divergence oracle + auto-bisect + MCP-fleet** — the combination none of them has. | If a framework-native tool reaches *faithful cross-version replay + bisect* first → **pivot to a thin OTel viewer/analyzer** layered on top of their checkpoints. |
| **R7** | **Provider-side model drift / retirement.** The same model id behaves differently over time; OpenAI's `system_fingerprint` changes a few times a year and reproducibility is best-effort even with a seed. ([OpenAI Cookbook — Reproducible outputs](https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter); [OpenAI — Deprecations](https://developers.openai.com/api/docs/deprecations)) | H | M | Fork against an old recording produces wildly different continuations; model id/fingerprint changed. | **Playback is immune — lean on it.** Store model id + fingerprint; warn on fork when the model has drifted. | Not a replay-killer under playback. Only kill **fork** if drift makes counterfactuals meaningless. |
| **R8** | **Storage volume at fleet scale.** Full prompt + completion plus hundreds of spans per run, KB–MB each — roughly an order of magnitude costlier than web observability. ([Coding Protocols — AI workloads observability cost](https://codingprotocols.com/blog/ai-workloads-observability-cost)) | H | M | Per-run storage blows the budget on a realistic agent. | Content-address + dedupe; columnar + ZSTD; head/tail sampling; retention policies; object storage keyed by hash. | If per-run storage cannot hit a viable budget without dropping replay-needed data → **on-demand recording** (only flagged/failing runs), not fleet-wide always-on. |
| **R9** | **ML cold-start.** Zero labeled failures at launch; weak supervision trades accuracy for speed and bad labeling functions inject noise; a LoRA explainer needs ~1k+ quality examples. ([Snorkel — Weak supervision](https://snorkel.ai/data-centric-ai/weak-supervision/); [Particula — How much data to fine-tune an LLM](https://particula.tech/blog/how-much-data-fine-tune-llm)) | H | M | Clusters/explanations no better than a simple baseline. | **Defer ML to Phase 2.** Start with deterministic heuristics + embeddings + a prompted general LLM over the *replayed* trace; harvest labels from bisect. | If clusters/explanations don't beat an embedding + prompted-LLM baseline → **cut ML / LoRA**. |
| **R18** | **Hidden global / module state & monkeypatching.** Import-time singletons, module globals, LRU caches, patched SDKs, and connection pools are invisible nondeterministic inputs — a nastier face of R2. | M | M | Replay diverges and the source traces back to global/patched state. | Snapshot/seed known globals; document unsupported patterns; **detect offenders** and warn. | Same as **R2** — pivot to bounded-scope replay if unfixable. |
| **R12** | **Recorder perturbs the agent (Heisenbug).** Interposing changes timing/interleaving, so the recorded run differs from production. | M | M | Recording materially alters agent behavior on realistic workloads. | Keep the hot path cheap (async batched export); record **causal order, not wall-clock**. | If recording materially alters behavior on realistic workloads → **sampled / opt-in recording**. |
| **R13** | **Streaming (SSE) fidelity.** We must record and replay token/tool-call deltas, chunk boundaries, partial JSON, and mid-stream errors — and chunk boundaries are themselves provider-nondeterministic. | M | M | Streaming-dependent behavior can't be reproduced from recorded frames. | Record **raw SSE frames verbatim**; treat the reassembled result as the canonical boundary. | If raw-frame replay can't reproduce streaming-dependent behavior → **guarantee only the final assembled message**. |
| **R14** | **Auto-bisect assumes alignable traces.** "First diverging decision" only exists if traces are comparably structured; under nondeterminism two independent runs diverge everywhere. | M | M | No stable "first divergence" across runs of the same inputs. | Bisect over **replayed (deterministic) traces of the same recorded inputs**, not two independent live runs; require a shared prefix. | If a stable "first divergence" is unattainable → **downgrade bisect to a diff-viewer**. |
| **R15** | **Local / OSS model determinism — GPU float.** Re-executing local models reintroduces GPU nondeterminism (non-associative FP, dynamic batching, cuDNN/cuBLAS heuristics); byte-exact is unattainable without batch-invariant kernels at ~60% throughput cost. ([Thinking Machines — Defeating Nondeterminism](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/); [arXiv 2408.05148](https://arxiv.org/pdf/2408.05148)) | M | M | GPU re-execution of a fixed prompt yields > 1 unique output. | **Never re-execute local models on the replay path — play them back** like any other boundary. | Re-executing local models *faithfully* is **out of scope for v1**. |
| **R16** | **OTel GenAI convention churn.** No GenAI attribute is Stable — all are "Development"; repos have moved and dual-emission is needed. ([John Hodge — OTel GenAI semantic conventions](https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/)) | M | M | A convention change breaks our export/ingest. | **Version the recording schema independently**; adapt at the edges; pin a convention version. | Not a killer — **freeze the internal schema** and treat OTel purely as an export format. |
| **R17** | **MCP spec churn.** The 2026-07-28 revision removes protocol-level sessions. ([MCP — 2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)) | M | M | An MCP revision breaks the adapter again. | **Abstract MCP behind an adapter**; don't hardwire session semantics. | If MCP keeps breaking → ship the **vendor-neutral core first**; MCP adapter is a **pluggable extension, not a v1 dependency**. |
| **R19** | **Tokenizer / temperature / sampling edge cases.** Mostly moot under playback; matters only for fork and drift. `temperature=0` is not deterministic in practice. | L | M | Fork continuations vary even at nominally deterministic settings. | Record all sampling params + seed as **metadata**; use them only to *characterize*, never to promise determinism. | **N/A for playback.** |

**Why this ordering matters:** the top cluster (R2, R3, R4, R5, R1) are all facets of the same core bet — *can we make playback bit-exact and can we prove it?* They are validated or falsified first, in Weeks 1–3, by the spikes below. Everything lower in the register only matters if that core bet holds.

---

## Where this could be genuinely IMPOSSIBLE — cheap spikes for Weeks 1–3

Each spike is a throwaway experiment designed to **fail fast**. It has one job: prove a load-bearing assumption or kill it cheaply, before we commit engineering months. Each carries an explicit **pass/fail bar**. They are ordered so the cheapest, most fundamental failures surface first.

**Spikes A and B together are the go/no-go gate for the whole project.** They are scheduled in the [Month-1 roadmap](./roadmap-6-months.md) and gate everything downstream. If we cannot demonstrate bit-exact playback with a loud divergence oracle on a trivial agent in the first two weeks, everything downstream is built on sand.

### Spike A — "Is playback actually bit-exact?" (R2 / R3 — the go/no-go). RUN FIRST.
Build a throwaway recorder for a 5–10 step OpenAI agent with a single tool. Record once, then replay **50×** in pure playback. A divergence detector hashes the full input to every boundary on each replay.
- **PASS:** 50/50 replays are **byte-identical** AND the detector never emits a false ✓.
- **FAIL:** *any* silent divergence → trigger the **R2/R3 pivot** (bounded-scope replay and/or reposition as a viewer).

### Spike B — "Does replay survive un-interposed nondeterminism?" (R2 / R18)
Add `time.time()`, `random`, `uuid4`, and dict-order-dependent logic to the agent **without teaching the recorder about them**. Then replay.
- **PASS:** the divergence detector **catches and loudly fails** on each un-captured source.
- **FAIL:** silent divergence → we have **no working oracle**, which makes **R3 fatal**. (This spike tests the oracle, not the capture: we *want* divergence here; the pass condition is that we *detect* it.)

### Spike C — "Local-model determinism, CPU vs GPU" (R15)
Run a 1–8B model **100×** on a fixed prompt at `temperature=0`, on both CPU and GPU; count unique outputs. This spike **measures**, it does not pass/fail.
- **Outcome:** if GPU unique outputs > 1 (the expected result), **ban local-model re-execution from the replay path** — local models are played back, never re-run.

### Spike D — "Concurrent tool-call replay" (R5)
An agent fires 3 tool calls via `asyncio.gather`. Record, then replay **20×**, checking that boundaries match correctly under varied arrival order.
- **PASS:** 20/20 replays match by **content / causal key**.
- **FAIL:** concurrent agents are unsupported → **scope the guarantee to sequential agents only**.

### Spike E — "Refactor survival" (R4)
Record against commit *N*. Perform a realistic refactor into commit *N+1* (rename a tool, add a log line, reorder independent calls). Replay the *N* recording against *N+1* code.
- **PASS:** replay **succeeds** via semantic keying, **OR** fails **loudly** with a clear, actionable message.
- **FAIL (silent mismatch):** **SHA-pin recordings** and drop the "debug old incidents against new code" promise.

### Spike F — "Redaction recall + storage footprint" (R6 / R8)
Seed **20 secret formats** into prompts and tool args. Run redaction, then secret-scan the *stored* recording. Separately, measure bytes/run for a 30-step agent.
- **PASS:** **20/20** secrets redacted *before* storage AND per-run footprint is within the stated budget after dedupe + ZSTD.
- **FAIL:** any secret leaks → **content capture off by default**; footprint too large → **on-demand recording only**.

### Spike G (optional) — "SSE fidelity" (R13)
Record raw SSE frames from a streamed tool-calling response, replay them, and confirm the reassembled tool-call JSON is **byte-identical**.
- **PASS:** reassembled tool-call JSON matches byte-for-byte.
- **FAIL:** downgrade the streaming guarantee to the final assembled message (per R13).

---

## Assumptions we are betting the whole project on

Stated plainly so they can be attacked. If one of these is false, the plan must change — several map directly to the spikes above.

1. **Replay is playback, not re-execution.** The model is never re-run on the faithful replay path. (The core law.)
2. **We can enumerate AND interpose on every nondeterministic boundary** — clock, RNG, `uuid`, env, filesystem, network, tool I/O, globals. **This is the riskiest bet** (tested by Spikes A and B).
3. **We can *detect* divergence, not just hope for faithfulness.** The divergence oracle is real and reliable (Spike B).
4. **Target agents are mostly sequential, or use content-addressable concurrency** (Spike D).
5. **Users accept per-commit / SHA-pinned recordings** as the default contract (Spike E).
6. **Redaction is high-recall and happens pre-storage** (Spike F).
7. **ML is optional garnish, not the product.** The product is faithful record + playback + scrub.
8. **Three people can ship faithful record + playback + scrub in 6 months — ONLY if fork, bisect, and ML are deferred** to Phase 2.

---

## How this informs the roadmap

The register and the spikes drive the plan directly:

- **Weeks 1–3 are the go/no-go gate.** Spikes A + B are a *literal* gate in the [6-month roadmap](./roadmap-6-months.md). If we cannot show bit-exact playback with a loud divergence oracle on a trivial agent, we do not proceed to build — we pivot (bounded-scope replay) or reposition (trace viewer) per R2/R3.
- **The MVP is scoped by R1.** Month 1–3 delivers *only* deterministic record + playback + scrub. Fork, bisect, and ML are explicitly Phase 2 and are the first things cut if the core slips (see the [milestones & exit criteria](./milestones-and-exit-criteria.md)).
- **Every KILL/PIVOT criterion is a pre-committed decision.** When an early-warning signal fires, we execute the pivot rather than debating it mid-crisis. The [milestones & exit criteria](./milestones-and-exit-criteria.md) doc turns these into dated checkpoints.
- **The month-3 kill switch is real.** If replay is not bit-exact on ≥1 real framework by the end of Month 3, we cut fork + bisect + ML and ship a faithful recorder — a smaller product that still tells the truth, which is the whole point.

The through-line: **a debugger that quietly lies is worse than no debugger.** Every risk, every spike, and every kill criterion in this document exists to make sure Rewind never becomes that.
