# ADR-0008: Rewind owns its recording schema; OpenTelemetry is an export/interop format

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma, @aasthaaa25, @kartikdua24

## Context

Rewind positions itself as *vendor-neutral*, built on the OpenTelemetry GenAI semantic
conventions. But research into the current state of those conventions
([`../plan/tech-stack-and-oss-map.md`](../plan/tech-stack-and-oss-map.md)) found that, as
of mid-2026, **no GenAI span, metric, or attribute is marked Stable** — every one is
"Development." The conventions were split into a separate repository in 2026 with no
versioned releases, attributes have been renamed across minor versions
(`gen_ai.system`→`gen_ai.provider.name`, `prompt_tokens`→`input_tokens`), and message
content moved from events to span attributes. Frameworks emit several generations of the
conventions simultaneously.

Coupling Rewind's on-disk recording format directly to this moving target would make
recordings fragile and force schema migrations every time upstream churns. Yet
interoperability with the OTel ecosystem (viewing runs in Jaeger/Tempo/Phoenix, ingesting
existing traces) is a genuine advantage worth keeping.

The recording format is also the **load-bearing contract** between the three engineers
(capture writes it; DX and ML read it), so it must be stable internally.

## Decision

**We will define and own an internal recording schema, and treat OpenTelemetry /
OpenInference as an edge format for export and ingest — never as the source of truth.**

- The recording is our own versioned schema: a **boundary log** (the ordered
  nondeterministic reads), a content-addressed blob store, a per-boundary **hash-chain**
  for integrity + divergence detection, and metadata (model ids, seeds, code
  fingerprint). It is versioned independently of any external spec.
- At the edges, we **normalize inbound** OTel/OpenInference spans into our schema on
  ingest, and **render outbound** OTLP so recordings open in existing OTel backends.
- The internal schema is **frozen via ADR ~Week 8** of the plan and changed only by a
  superseding ADR thereafter.
- We publish a "tested-with" matrix of framework/convention versions rather than
  claiming blanket compatibility.

## Consequences

- **Easier:** recordings are stable across OTel churn; the internal contract between the
  three workstreams is firm; replay depends only on our own format, not on unstable
  external field names.
- **Easier:** we still get ecosystem interop (view in Jaeger/Phoenix, ingest existing
  traces) through the edge adapters.
- **Harder / obligations:** we must write and maintain normalization adapters at the
  edges, and keep them current with the ≥2 convention generations frameworks emit; we
  own a schema-migration story for our own format across versions.
- **Cost:** "vendor-neutral on OpenTelemetry" is now a claim about *interop at the
  edges*, not about storing raw OTel — messaging must reflect that honestly.

## Alternatives Considered

- **Use OTel GenAI attributes as the on-disk format.** Rejected: the conventions are
  unstable/unversioned and lossy for replay; our format would inherit every upstream
  breaking change.
- **Invent a format and ignore OTel entirely.** Rejected: throws away free ecosystem
  interop and a bootstrap ingest path, and weakens the vendor-neutral positioning.
- **Wait for the conventions to stabilize before choosing.** Rejected: stabilization has
  no committed date; the project cannot block on it.
