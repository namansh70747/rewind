# ADR-0003: Embedded, local-first storage

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma (@namansh70747)

## Context

A recording is not small. For each run Rewind must persist an authoritative replay
index (the ordinal boundary keys), large raw payloads (full LLM requests/responses,
streaming chunks, tool results), analytics-friendly columnar data, and vector
embeddings for the ML layer. These are four genuinely different access patterns:
point lookups by key, big-blob storage with dedup, columnar aggregation, and vector
similarity search.

Two cross-cutting constraints shape the choice:

- **Faithful replay demands the exact payload bytes**, so the store must hold full,
  untruncated content — cheaply enough that recording every run is viable.
- **Rewind is an open-source developer tool.** The first-run experience must be
  `pip install` and go. Requiring a developer to stand up and operate a database server
  before they can record their first agent would kill adoption, and it would also make
  the tool awkward to run inside CI or on a laptop.

There is also a privacy dimension: payloads can contain PII, so wherever they live
must support redaction on export and a structure-only mode.

## Decision

**We will use an embedded, zero-server, local-first storage stack**, composed of
purpose-fit embedded engines:

- **SQLite** — run metadata and the **authoritative replay index**.
- **Content-addressed `zstd` blob store** — the real payload bytes, compressed and
  **deduplicated across runs** by content hash (loops, retries, and repeated prompts
  cost storage once).
- **DuckDB** — analytics and aggregate queries over runs.
- **LanceDB** — the vector store for embeddings used by the ML layer.
- **OTLP export** — emit spans to Jaeger / Tempo for free structural viewing.

PII is captured **raw locally** but **redacted on export**, and a **structure-only
mode** is available for environments that must never persist raw content.

## Consequences

**Easier**

- Zero operational burden: no server to provision, secure, or pay for; `pip install`
  and the tool works on a laptop or in CI immediately.
- Each engine is used for what it's best at, and content-addressing gives large,
  automatic cross-run dedup — critical because recordings are payload-heavy.
- Local-first keeps raw PII on the user's machine by default, which is the safe
  default; export is the moment redaction applies.

**Harder / costs**

- Four embedded engines mean **four on-disk formats** to manage, migrate, and keep
  consistent for a single logical run.
- Local-first is single-node by default; multi-user sharing and centralized fleet
  analytics need an explicit path (addressed later — run sharing is a P5 concern), so
  collaboration isn't free.
- We own retention/GC ourselves (also P5); nothing prunes old runs automatically until
  we build it.

## Alternatives Considered

- **A hosted database / SaaS backend.** Would give collaboration and centralized fleet
  analytics out of the box. Rejected: it forces network dependency and (typically)
  cost onto every user, contradicts the local-first privacy posture (raw PII would
  leave the machine), and adds an operational service to an open-source tool that
  should just run.

- **A single Postgres + pgvector server.** One server covering relational, analytical,
  and vector needs is operationally simpler than four engines *in the large*, but it
  reintroduces the exact barrier we are avoiding: the user must run and manage a server
  before recording anything. Rejected for the pre-alpha/dev-tool context; the
  embedded stack wins on zero-setup and portability, and each embedded engine
  outperforms a general server at its specific access pattern.
