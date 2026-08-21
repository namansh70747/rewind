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
  replays it bit-exact offline. Scope: synchronous `httpx.Client`, HTTP boundary only for
  now (non-HTTP nondeterminism is flagged by the oracle rather than silently mis-replayed);
  global clock/uuid/rng shims, async, and a `fr record -- python agent.py` wrapper follow.
  Advances #16.
- **Redaction-on-write** (`flightrecorder.redaction`): secrets/PII (API keys, tokens,
  JWTs, emails) are scrubbed from request URLs/bodies and responses **at capture time**,
  so the raw values never reach the boundary log or the store. Redaction is deterministic,
  so replay stays bit-exact on the redacted recording. Request headers are still not
  captured (so `Authorization` never lands there). Fulfills a `SECURITY.md` commitment
  and mitigates risk R6.

[Unreleased]: https://github.com/namansh70747/rewind/commits/main
