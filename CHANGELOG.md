# Changelog

## Acceptance hardening — 2026-11-14

- Concurrent replay rejects wrong final outputs and fingerprints.
- Overlapping socket guards share a thread-safe lifetime; explicit live access is context-local.
- Candidate explanations no longer assert that sampling or hallucination is proven by a weak label.
- Blinded baseline export excludes answers; synthetic classifier inputs no longer include target family labels.
- Strict docs links, original release-gate mapping and measured capture-overhead evidence are corrected.


## Unpublished Month 6 (P5) — 2026-11-14

Shipped weeks 23–26 on the `feat/month-6-lora-explainer` branch stacked on Month 5.

- **`fr explain <run_id>`** — deterministic plain-English root-cause narration from
  the classifier label, bisect divergence class, or weak label.  No model is called;
  every sentence is a fixed template keyed on the nine-class taxonomy.  The
  `lora_status` field records the LoRA deferral decision (ADR-0014).
- **`fr gc`** — delete old runs by `--keep-last N` or `--max-age-days D`, then sweep
  unreachable blobs via `store.garbage_collect()`.  `--dry-run` previews without
  changing state.
- **`fr benchmark-replay`** — measure replay throughput for a saved run; structured
  `rewind.benchmark.v1` evidence record.
- **Concurrent replay** (`month6.concurrent_replay`) — replay a cassette N times in
  parallel threads; `ConcurrentReplayResult` reports `passed`, `failed`, elapsed time,
  and throughput.
- **ADR-0014** — documents the Month 6 scope, the LoRA deferral rationale, and the
  retention / GC design.
- **`tests/test_month6.py`** — 20 unit tests covering `explain`, `concurrent_replay`,
  `retention_gc`, `benchmark_replay`, and the `fr explain` / `fr gc` CLI commands.
- **Month 6 acceptance workflow** (`.github/workflows/month6-acceptance.yml`) — CI
  gate for the explainer schema, concurrent-replay pass rate, and GC correctness.

No claim of research priority is made.  LoRA fine-tuning remains deferred pending a
reviewed labeled corpus.  Code Owner review, CI tag, and final real-data gates remain
open.

## Unpublished actual-model investigation — 2026-10-08

Added a local-model capture and controlled intervention example. Four recordings
passed 200 server-off replays; the ineffective live quote fork and successful
explicit decision intervention are separately reported. The dashboard identifies
recorded model responses with simulated tools. Model accuracy and real-fleet
release acceptance remain unclaimed.


## Unpublished acceptance hardening — 2026-10-08

Replaced model-written cluster claims with validated evidence-ID selection and
deterministic explanations, qualified against actual local Ollama inference.
Hardened corpus fixtures against malformed/duplicate manifests, path escapes,
corrupt chains and runtime failures. Added controlled live-provider capture
harnesses, a one-command local acceptance runner and exact completion inputs.
Updated stale source documentation for BLAKE3/zstd compatibility.


## Unpublished model qualification and platform preparation — 2026-10-08

Actual local Ollama/Qwen inference with pinned model-digest evidence and explicit
semantic-quality failures; reproducible smoke example; bounded summary generation;
portable isolated-wheel smoke and Ubuntu/Windows/macOS CI jobs; frozen lockfile
installs; recorded/current SHA diagnostics for script drift. No publication claim.

## Unpublished release workflow hardening — 2026-10-08

Added paced stream replay, scoped custom redaction, local Ollama summary contract,
OTLP protobuf export, actual Perfetto parser qualification, digest-checked release
evidence, Pages deployment workflow and protected PyPI publishing preparation.
Missing real-data/review gates still block publication.


## Unpublished integration completion — 2026-10-08

Managed MCP v1 stdio/HTTP lifecycle; isolated async LangGraph replay; async error
and cancellation terminals; source/concurrency script flags; aligned dashboard;
quoted and escaped SSE credential fixes; safe original chunk bytes; explicit policy
editor; held-out baseline scoring; actual BGE/LanceDB/HDBSCAN/UMAP smoke; semantic
alignment and fingerprint-checked vector search; navigable docs and synthetic gallery.
90 local tests plus separate model/browser checks. Publication gates remain open.

## Unpublished roadmap candidate — 2026-10-08

BLAKE3/zstd with legacy reads; async completion-order capture; tool/source shims;
transport-failure replay; persisted checkpoints; safe policy/script forks; Textual
and trace exports; LangGraph/MCP exchange adapters; alignment and query DSL; grouped
classifier and fleet map. See docs/roadmap-status.md for partial features and gates.
No tag or public release has been created.


All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> [!NOTE]
> Rewind is **pre-alpha** (`0.0.x`). While the major version is `0`, anything may
> change at any time and the public API is not yet stable, per SemVer's
> initial-development clause.

## [Unreleased]

### Fixed

- CLI startup preserves legacy terminal encodings while escaping unsupported
  characters, preventing Windows redirected help/demo UnicodeEncodeError.
  Added a cp1252 subprocess regression.

### Added

- Month 5 failure intelligence on local recordings: named timeline queries
  (`every tool error`, `every retry`, `first context > N tokens`), explicit
  retry/cost features, `fr match` for nearest cluster plus a similarity-weighted
  weak cause, and `fr eval --budget` which fails when a candidate budget changes
  recorded outcomes.
  Synthetic corpus checks live in `tests/test_month5.py`. The real 672-tool fleet
  and a prompted-LLM baseline are still required before the Month 5 gate is closed.
- Repository scaffolding, governance, CI, and complete design documentation.
- **Phase-0 walking skeleton**: the `flightrecorder` core (Session/boundary hash-chain,
  httpx transport capture, deterministic replay with a network kill-switch),
  content-addressed SQLite run storage, and the `fr` CLI (`record`, `show`, `verify`,
  `runs`). Provider-neutral across OpenAI, NVIDIA, and Anthropic. Verified end-to-end:
  a real run replays bit-for-bit offline with zero API calls.
  - Scope: records the **bundled example agent** (`fr record --provider …`); capturing an
    arbitrary, unmodified agent (`fr record -- python agent.py`) is Phase 1.
  - **Provisional recording format (not frozen).** Uses stdlib `blake2b` + `zlib` rather
    than the ADR-0003 / roadmap target of BLAKE3 + zstd, to keep the skeleton
    dependency-free. The on-disk format is frozen later (~Week 8); early recordings may
    need migration on the switch.
- **Global capture of an unmodified agent** (`flightrecorder.capture`): `with capture(store)
  as cap: …` records any code that uses plain `httpx` — no `flightrecorder` imports in the
  agent — by wrapping `httpx.Client`'s transport for the duration of the block; `verify_run`
  replays it bit-exact offline. Covers `httpx.Client` **and** `httpx.AsyncClient` (base
  transport + proxy `_mounts`); async agents are driven/replayed with `asyncio.run(...)`.
  Scope: HTTP boundary only for now, and **serialized** — concurrent boundaries
  (`asyncio.gather` of HTTP calls) are detected and fail loud rather than corrupt the
  hash-chain. Non-HTTP nondeterminism is flagged by the oracle rather than silently
  mis-replayed; global clock/uuid/rng shims, concurrent replay, and a
  `fr record -- python agent.py` wrapper follow. Advances #16.
- **Streaming (SSE) capture & replay**: streamed responses are recorded as their decoded
  chunk sequence (plus `content-type`), so a `client.stream(...)` agent that parses
  Server-Sent Events reproduces bit-exact on replay — sync and async. The chunk fields are
  additive (single-chunk responses are unchanged). Response headers beyond `content-type`
  are still not captured.
- **Redaction-on-write** (`flightrecorder.redaction`): secrets/PII (API keys, tokens,
  JWTs, emails) are scrubbed from request URLs/bodies and responses **at capture time**,
  so the raw values never reach the boundary log or the store. Redaction is deterministic,
  so replay stays bit-exact on the redacted recording. Request headers are still not
  captured (so `Authorization` never lands there). Fulfills a `SECURITY.md` commitment
  and mitigates risk R6.
- **Auto-bisect v1** (`flightrecorder.bisect`, `fr bisect <run_a> <run_b>`): finds the first
  diverging decision between two recordings and classifies it — *same input → different
  output* (the decision diverged) vs *different input → different output* (upstream cause).
  Step-aligned (assumes a shared prefix); sequence alignment for insert/delete is a later
  phase. Advances the auto-bisect pillar (roadmap M4).

[Unreleased]: https://github.com/namansh70747/rewind/commits/main

## Local alpha 0.1.0 (proposed release) - 2026-10-08

### Added
- Offline failure-to-recovery demo with verified runs and interactive HTML timeline.
- Safe explicit-mock counterfactual forks with provenance; prefix state inspection.
- Versioned checksummed JSON import/export and synthetic evaluation harness.
- Trusted script recording and source/stdout-aware verification; event similarity.
- Faculty demo/viva guide, acceptance tests and optional browser smoke test.

### Fixed
- Mutable agent values could corrupt recorded boundaries.
- Replay validates sequences/fingerprints and guards ordinary Python socket calls.
- SQLite saves are atomic and content-addressed blobs checked when loaded.
- UTF-8 split across SSE chunks, content-type preservation, transport closure.
- Sensitive named JSON fields and token-bearing HTTP path labels are redacted.
- Identical boundaries with different final outputs now report divergence.
- README status and guarantees now distinguish implemented features from plans.
