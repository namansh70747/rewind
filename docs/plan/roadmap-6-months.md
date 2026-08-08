# The 6-Month Roadmap — Week by Week

This is the executable core of the plan: **26 weeks**, grouped into **6 monthly milestones**, each week with a theme, **per-person targets** (E1 = Capture & Replay Core, E2 = Developer Experience, E3 = ML/Data/Eval — see [`team-and-cadence.md`](./team-and-cadence.md)), and a hard **exit criterion**.

**How to read it:** a week isn't "done" until its exit criterion is green in CI. Fixed time, variable scope — if a week slips, cut *down the ladder* (see [`README.md`](./README.md#the-scope-cut-ladder-what-we-drop-first-if-we-fall-behind)), never slip the P0 core. The milestone **gates** are the go/no-go points defined in [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md).

Legend: 🚦 = go/no-go gate · 🔒 = a contract is frozen this week · ⭐ = the demo-defining deliverable.

---

## Month 1 — Foundations & the Go/No-Go (Weeks 1–4)

**Milestone M1 goal:** prove the core thesis is possible, then land a walking skeleton that records one real agent run and replays it bit-exact from the CLI. Everything downstream hangs off this thread.

### Week 1 — Prove bit-exact playback (🚦 the whole project rides on this)
- **E1:** Build a *throwaway* recorder for a 5–10-step OpenAI agent (one tool) at the `httpx` transport layer. Run **Spike A**: record once, replay 50× in playback mode with a boundary-hash divergence check.
- **E2:** Stand up the dev loop — `uv` env, CI green on the skeleton, the `fr` CLI shell, a throwaway agent fixture, and a scripted way to run/re-run spikes.
- **E3:** Start the **test corpus** — collect 10–15 diverse real agent runs (varied tools, lengths, providers) as spike inputs and future regression fixtures.
- **Exit criterion:** Spike A result recorded — **PASS = 50/50 byte-identical replays, zero false ✓** from the oracle. (Reference: [`risks-and-spikes.md`](./risks-and-spikes.md) Spike A.)

### Week 2 — De-risk the rest, then commit (🚦 go/no-go decision)
- **E1:** Run **Spike B** (inject un-captured `time`/`random`/`uuid4`/dict-order → replay must *fail loud*), **Spike D** (concurrent `asyncio.gather` tool calls), **Spike E** (refactor survival).
- **E2:** Run **Spike F** (redaction recall on 20 seed secrets + per-run storage footprint); sketch the timeline-UI approach (Textual + Perfetto export vs web).
- **E3:** Run **Spike C** (local-model determinism CPU vs GPU — *measure*, to justify banning re-execution from the replay path).
- **Exit criterion:** all spikes have a written pass/fail verdict; a **go / pivot decision** is recorded as an ADR. If A+B failed → pivot to "faithful recorder + trace viewer" and re-baseline the roadmap.

### Week 3 — Walking skeleton, part 1: capture + store
- **E1:** Real (non-throwaway) capture: `httpx` transport interceptor for OpenAI chat; determinism shims (`time-machine` for clock; recorded `uuid4`/RNG seeds); a `@fr.tool` decorator; write to SQLite(WAL) + a content-addressed blob dir.
- **E2:** `fr record -- python agent.py` wraps a run; `fr show <run>` prints the decision timeline (Rich tree). Package/CLI plumbing.
- **E3:** Define the **faithfulness metric** and the CI harness that will run the corpus through record→replay→verify each week.
- **Exit criterion:** `fr record` produces a persisted recording for the fixture agent; `fr show` renders its boundaries.

### Week 4 — Walking skeleton, part 2: playback + verify (⭐ + M1 gate)
- **E1:** The playback engine (`REEXEC_REPLAY`) serves recorded values by ordinal key; the **network kill-switch** raises on any un-served outbound call; `fr verify` re-runs and asserts the replayed boundary sequence matches. Draft the **log-format ADR**.
- **E2:** `fr verify <run>` UX (clear ✓/✗, first-divergence message); wire the round-trip into CI as the canary test.
- **E3:** Run the corpus through the skeleton; report faithfulness % and any silent-divergence findings.
- **Exit criterion (M1 gate):** ⭐ `fr verify <run>` proves the fixture run **replays bit-exact with zero API calls**, and `fr show <run>` prints the timeline — green in CI.

---

## Month 2 — Faithful Recorder & Verification (Weeks 5–9)

**Milestone M2 goal:** turn the skeleton into a *trustworthy* recorder — broad capture, streaming, multiple providers, a loud divergence oracle, safe redaction, and a **frozen log format**.

### Week 5 — The divergence oracle (fail-loud faithfulness)
- **E1:** Implement the boundary **hash-chain** (`h_i = H(h_{i-1} ∥ canon(req_i) ∥ canon(resp_i))`, BLAKE3 + canonical JSON — see [`algorithms-and-math.md`](./algorithms-and-math.md) §1); replay recomputes it and hard-fails at the first mismatch, naming the exact boundary.
- **E2:** Surface "replay verified ✓/✗" as a first-class CLI/UI output; a `--strict` flag.
- **E3:** Add adversarial divergence cases to the corpus (deliberately un-captured sources) to prove the oracle fires.
- **Exit criterion:** any injected divergence is caught and localized to the exact boundary; **no silent divergence** in the corpus.

### Week 6 — Streaming (SSE) capture & replay
- **E1:** Record raw SSE frames verbatim (chunk bytes + order + inter-chunk timing); replay reconstructs the async iterator; the *reassembled* message is the canonical boundary and its hash must match.
- **E2:** Timeline renders streamed tool-call assembly; `fr show` handles partial/streamed decisions.
- **E3:** Add streamed + tool-calling runs to the corpus (Spike G).
- **Exit criterion:** a streamed tool-calling run replays byte-identical (reassembled) with zero API calls.

### Week 7 — Multi-provider + tool boundary + loops/retries
- **E1:** Anthropic via the same `httpx` transport; formalize boundary matching with `occurrence_index` so loops/retries (incl. recorded failures) replay correctly ([`algorithms-and-math.md`](./algorithms-and-math.md) §2); capture env/config reads.
- **E2:** Provider-agnostic timeline; `fr` works unchanged across OpenAI/Anthropic.
- **E3:** Add multi-provider + retry-heavy runs to the corpus; track faithfulness per provider.
- **Exit criterion:** an unmodified OpenAI *and* an Anthropic agent both record & replay bit-exact; a retry loop replays its recorded failures in order.

### Week 8 — Content-addressed storage + 🔒 freeze the log format
- **E1:** BLAKE3 content-addressing + `zstd` compression + cross-run dedup + ref-counted GC ([`algorithms-and-math.md`](./algorithms-and-math.md) §4). **Freeze the recording log format via ADR.** 🔒
- **E2:** `fr` bundle export/import (a recording is a portable, shareable artifact — the "recording-as-a-URL" idea from replay.io).
- **E3:** Measure storage footprint/run after dedup+compression against the Spike-F budget.
- **Exit criterion (🔒):** log-format ADR merged; identical payloads stored once; a recording round-trips export→import and still verifies.

### Week 9 — Redaction, completeness audit (M2 gate)
- **E1:** Redaction-on-write (secrets/PII scrubbed *before* storage; deterministic secret placeholders so replay still works); a **boundary-coverage audit** that lists any outbound I/O observed but not served on replay.
- **E2:** `fr doctor` / coverage report surfacing un-instrumented I/O; redaction config.
- **E3:** Secret-scan the stored corpus (target: 0 leaks); publish the Month-2 faithfulness report.
- **Exit criterion (M2 gate):** any unmodified OpenAI/Anthropic agent records → replays bit-exact → verifies, with the coverage audit clean and **0 secrets** in stored recordings.

---

## Month 3 — Time-Travel & Counterfactual Fork (Weeks 10–13)

**Milestone M3 goal:** make recordings *navigable* (scrub to any step, inspect state) and *interrogable* (fork a counterfactual) — safely.

### Week 10 — Replay-to-N + snapshots
- **E1:** Reconstruct agent state at step N via replay-to-nearest-snapshot-then-forward; periodic snapshots at the √N-optimal interval, COW/incremental deltas into the CAS ([`algorithms-and-math.md`](./algorithms-and-math.md) §5); schema'd state serialization.
- **E2:** `fr show <run> --at N` renders state at any step; groundwork for the scrubber.
- **E3:** Benchmark replay-to-N latency vs snapshot interval on the corpus; tune `k`.
- **Exit criterion:** jump to any step of a long run in bounded time with exact reconstructed state.

### Week 11 — Time-travel UI v1 (⭐ the demo surface)
- **E1:** Stable state-inspection API behind the UI; expose the hash-chain per step.
- **E2:** ⭐ Textual TUI scrubber (step forward/back, inspect prompt/response/tool I/O at each boundary) **and** a Perfetto-loadable trace export as the zero-build waterfall.
- **E3:** Usability pass on real corpus runs; feed missing fields back into the (now-frozen) schema via ADR if truly needed.
- **Exit criterion:** you can scrub a real recorded run's decision timeline and inspect any step, in the terminal and in Perfetto.

### Week 12 — Counterfactual fork + side-effect safety
- **E1:** `FORK(at, X)` — deterministic playback to N, inject a mutated boundary value, switch to **live** continuation saved as a *quarantined* forked run; a **side-effect policy engine** (tools classified read-only vs mutating; **mutating tools mocked by default** in fork mode; per-tool opt-in to go live).
- **E2:** `fr fork <run> --at N` UX; forked runs visually quarantined; a tool-classification manifest editor.
- **E3:** Eval-over-forks scaffolding (a fork is a controlled experiment: one variable changed).
- **Exit criterion:** scrub to step N, change a tool result, replay forward with dangerous tools mocked — no real side effect fires; the fork is saved as its own replayable run. *(Fork is labeled best-effort exploration, not "faithful.")*

### Week 13 — LangGraph + OTel interop (M3 gate)
- **E1:** Ensure capture works under a LangGraph event loop (async completion-order recording).
- **E2:** LangGraph adapter v1 (checkpointer/callback) so Rewind records the threads LangGraph already checkpoints; OTel/OpenInference **export** (recordings are also valid traces) and **ingest** of existing traces.
- **E3:** Compare a LangGraph "time travel" resume (re-runs live) vs a Rewind replay (bit-exact) as a positioning artifact.
- **Exit criterion (M3 gate):** a LangGraph agent records/replays/forks through Rewind; a recording opens in an OTel viewer (Jaeger/Phoenix) unchanged.

---

## Month 4 — Auto-Bisect & Fleet Capture (Weeks 14–18)

**Milestone M4 goal:** given a passing and a failing run, pinpoint and *name* the first diverging decision; capture across a multi-server MCP fleet.

### Week 14 — Auto-bisect v1 (hash-chain binary search)
- **E1:** Expose the per-step hash-chain for two aligned runs; binary-search the first differing `h_i` in O(log N) ([`algorithms-and-math.md`](./algorithms-and-math.md) §1).
- **E2:** `fr bisect <pass> <fail>` CLI; first-divergence output.
- **E3:** Build labeled pass/fail pairs (flip one recorded tool result) as bisect ground truth.
- **Exit criterion:** for step-aligned pairs, `fr bisect` names the injected divergence step.

### Week 15 — Auto-bisect v2 (sequence alignment for insert/delete)
- **E1/E3:** Needleman–Wunsch/Smith–Waterman with a **semantic cost** (embedding cosine + structured tool-call diff) for runs that added/removed steps ([`algorithms-and-math.md`](./algorithms-and-math.md) §3; Biopython + RapidFuzz).
- **E2:** Side-by-side aligned timeline in the UI.
- **Exit criterion:** bisect localizes the first real divergence even when the two runs differ in length.

### Week 16 — Divergence taxonomy + diff UI (⭐)
- **E3:** Classify each divergence (`arg-hallucination`, `tool-choice`, `sampling-flake`, `tool-result-drift`, `retrieval-drift`, `loop`, `cost-blowup`, `truncation`…); this label doubles as a weak ML label.
- **E2:** ⭐ Side-by-side diff view naming the divergence in plain English, with the raw diff always shown.
- **E1:** Distinguish same-input→different-output (decision diverged) vs different-input→different-output (walk back).
- **Exit criterion:** on a real failing/passing pair, Rewind shows the first diverging decision + a named cause a human agrees with.

### Week 17 — MCP-fleet adapter
- **E1/E2:** Capture at the MCP JSON-RPC transport (record `tools/call` request/response frames) so *any* MCP server is recordable; abstract session semantics behind an adapter (insulate against MCP spec churn).
- **E3:** Add multi-server MCP runs to the corpus.
- **Exit criterion:** an agent driving multiple MCP servers records & replays bit-exact via the adapter.

### Week 18 — Concurrency/async fidelity + hardening (M4 gate)
- **E1:** Serialized-timeline replay + recorded completion-order for `asyncio.gather` fan-out ([`algorithms-and-math.md`](./algorithms-and-math.md) §2); document sequential-vs-concurrent guarantees.
- **E2:** Stabilize the CLI surface; error messages for code-drift ("recorded @ SHA X, replaying @ Y").
- **E3:** Month-4 faithfulness + bisect-accuracy report.
- **Exit criterion (M4 gate):** given a passing and a failing run of the same task, Rewind pinpoints and names the first diverging decision; concurrent-tool agents replay within the documented guarantee.

---

## Month 5 — ML Failure Intelligence & Eval Harness (Weeks 19–22)

**Milestone M5 goal:** across many recorded runs, cluster and root-cause failures; turn replays into a deterministic, zero-cost eval harness. *(This is P1/P2 — the first to be trimmed if the core needs the time.)*

### Week 19 — Features + embeddings + vector store
- **E3:** Feature extraction per run (steps, tool histogram, retries, tokens, cost, finish reasons, divergence class) + trajectory/error embeddings (`sentence-transformers` bge-small) → **LanceDB**.
- **E1:** Stable "run features" export from the log.
- **E2:** `fr similar <run>` (nearest failures) surfaced in the UI.
- **Exit criterion:** "find runs like this failure" returns sensible neighbors on the corpus.

### Week 20 — Clustering + failure map
- **E3:** HDBSCAN over embeddings + UMAP 2-D map ([`algorithms-and-math.md`](./algorithms-and-math.md) §6); Ollama summarizes each cluster to seed a taxonomy.
- **E2:** A failure-map view + cluster drill-down in the timeline UI.
- **Exit criterion:** failure clusters are coherent (a human agrees with the groupings) on the corpus.

### Week 21 — Weak-supervision labels + eval-over-forks
- **E3:** Heuristic labeling functions (Snorkel-style, but hand-written — snorkel is unmaintained) → a scikit-learn root-cause classifier with a real train/val/test split + per-mode F1; the **eval harness** runs a change against recorded runs as deterministic zero-cost fixtures.
- **E2:** `fr eval` (replay-as-fixture) integrated as a pytest-style CI gate (the DeepEval ergonomic).
- **Exit criterion:** the classifier beats a prompted-LLM baseline on held-out labels; `fr eval` gates a prompt/model change deterministically.

### Week 22 — Dogfood on the real fleet + query DSL (M5 gate)
- **E1/E2:** Point Rewind at the author's real 672-tool / 10-provider MCP fleet; a query DSL over the timeline ("every tool error", "first time context > N tokens" — the WinDbg-TTD idea).
- **E3:** "New failure → nearest known cluster + likely root cause" on real production runs.
- **Exit criterion (M5 gate):** across hundreds of real fleet runs, Rewind clusters failure modes and, for a fresh failure, surfaces "this matches cluster X" with a plausible cause.

---

## Month 6 — Cooldown, Hardening & Release (Weeks 23–26)

**Milestone M6 goal:** ship a clean, documented, installable `v0.1.0`; land the killer demo; take the stretch only if the core is solid — **cut, don't slip.**

### Week 23 — Performance & footprint
- **E1:** Capture-overhead pass (async batched export, ensure the recorder doesn't perturb the agent — R12); confirm storage footprint within budget.
- **E2:** Packaging: `pip install rewind`, enable the `fr` console script, cross-platform smoke.
- **E3:** Final faithfulness/perf benchmark report.
- **Exit criterion:** capture overhead measured and acceptable; `pip install rewind && fr --help` works on a clean machine.

### Week 24 — Docs, examples, and the killer demo (⭐)
- **E2:** ⭐ Record the end-to-end demo: **a real failing agent run → open the exact recording at the first diverging decision → fork "what if this tool returned X?" → watch it recover.** mkdocs site live; quickstart + 3 worked examples.
- **E1:** "Getting started" recorder API docs; supported-patterns matrix (sequential vs concurrent, which providers).
- **E3:** A public sample gallery of `.rewind` bundles (the OpenAI-Evals "shared registry" idea).
- **Exit criterion:** a newcomer can install Rewind and reproduce the killer demo from the docs alone.

### Week 25 — Stretch: LoRA explainer *or* deepen the core
- **E3:** *If and only if* the core is solid and labeled data exists: QLoRA fine-tune a small local model on bisect explanations to auto-narrate root cause ([`algorithms-and-math.md`](./algorithms-and-math.md) §6e/f). **Otherwise cut it** and harden replay/bisect instead.
- **E1/E2:** Burn down the top bugs from dogfooding; polish error messages and the code-drift story.
- **Exit criterion:** either a working "paste a failing run → plain-English root cause" narrator, **or** a documented decision to cut it plus a more robust core.

### Week 26 — Release v0.1.0 (M6 / final gate)
- **All:** Cut `v0.1.0` (tag, CHANGELOG, release notes); run the full demo end-to-end on a clean environment; retro; write the post-6-month backlog (concurrency v2, hosted sharing, more frameworks, production hardening).
- **Exit criterion (final gate):** `v0.1.0` is tagged and installable; the North-Star demo runs clean; the [`milestones-and-exit-criteria.md`](./milestones-and-exit-criteria.md) final Definition of Done is met.

---

## At a glance

| Month | Weeks | Milestone | Gate deliverable |
|---|---|---|---|
| 1 | 1–4 | Foundations & Go/No-Go | 🚦 spikes pass → walking skeleton: record→replay-exact→verify→timeline |
| 2 | 5–9 | Faithful Recorder & Verification | Any OpenAI/Anthropic agent replays bit-exact; divergence oracle; 🔒 log format frozen; 0 secrets |
| 3 | 10–13 | Time-Travel & Fork | Scrub any run; counterfactual fork with mutating tools mocked; LangGraph + OTel interop |
| 4 | 14–18 | Auto-Bisect & Fleet | Pinpoint & name the first diverging decision; MCP-fleet capture; async fidelity |
| 5 | 19–22 | ML Failure Intelligence | Cluster/root-cause failures on the real fleet; deterministic eval harness |
| 6 | 23–26 | Cooldown & Release | `v0.1.0` shipped; killer demo reproducible from docs; stretch LoRA or deepen core |

*If you fall behind: cut from the bottom of the [scope-cut ladder](./README.md#the-scope-cut-ladder-what-we-drop-first-if-we-fall-behind) (LoRA → ML clustering → MCP/LangGraph adapters → bisect → fork), and protect the P0 core at all costs.*
