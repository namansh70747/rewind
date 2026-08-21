# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> [!NOTE]
> Rewind is **pre-alpha** (`0.0.x`). While the major version is `0`, anything may
> change at any time and the public API is not yet stable, per SemVer's
> initial-development clause.

## [Unreleased]

### Added

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
- **Multi-provider + loops/retries (occurrence index)** — toward the M2 gate:
  - **Anthropic** records & replays bit-exact through the same httpx transport as OpenAI
    (only request shaping / response parsing differ, in `providers.py`); proven for both
    dialects (`Bearer` + `choices[].message` vs `x-api-key` + `content[].text`).
  - **Occurrence index** (`Boundary.occurrence`, algorithms-and-math §2): each boundary
    records the Nth time its `(kind, key)` appeared, so **loops and retries** — repeated
    calls to the same endpoint — replay in the exact recorded order. A retry that fails then
    succeeds replays its recorded failures **in order**; a run that reaches an endpoint a
    different number of times now fails loud with an occurrence-mismatch divergence. Derived
    from position (recomputed on load, not stored, not in the hash-chain), and surfaced in
    `fr show` as `·#1`, `·#2` on repeats. Env/config capture is deferred to a later slice.

[Unreleased]: https://github.com/namansh70747/rewind/commits/main
