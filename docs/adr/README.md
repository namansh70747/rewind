# Architecture Decision Records

This directory holds Rewind's **Architecture Decision Records (ADRs)** — short
documents that each capture one significant architectural decision, the context that
forced it, and the consequences of choosing it.

## What is an ADR?

An ADR records a decision that is expensive to reverse: a choice of architecture,
technology, or approach that shapes everything built afterward. Instead of that
reasoning living only in someone's head or a chat thread, an ADR writes it down so a
future reader (including the author) can understand **why** the system is the way it
is — and what alternatives were weighed and rejected. ADRs are immutable once
accepted: you don't edit a decision, you supersede it with a new one.

## Format (MADR-style)

Rewind uses a lightweight [MADR](https://adr.github.io/madr/)-style format. Every ADR
follows the same sections, defined by the [template](0000-template.md):

- **Title** — a short noun phrase naming the decision.
- **Status** — see the lifecycle below.
- **Context** — the forces, constraints, and problem that make a decision necessary.
- **Decision** — the choice that was made, stated plainly.
- **Consequences** — what becomes easier and what becomes harder as a result.
- **Alternatives Considered** — the serious options that were rejected, and why.

## Status lifecycle

| Status | Meaning |
| --- | --- |
| **Proposed** | Drafted and under discussion; not yet binding. |
| **Accepted** | Agreed and in force; the system reflects this decision. |
| **Superseded** | Replaced by a later ADR (which is linked from this one). |

## Index

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [0000](0000-template.md) | Template | — | — |
| [0001](0001-flagship-record-replay-time-travel-debugger.md) | Flagship: a record-replay + time-travel debugger | Accepted | 2026-08-08 |
| [0002](0002-vendor-neutral-otel-core-plus-fleet-adapter.md) | Vendor-neutral OTel core plus a fleet adapter | Accepted | 2026-08-08 |
| [0003](0003-embedded-local-first-storage.md) | Embedded, local-first storage | Accepted | 2026-08-08 |
| [0004](0004-python-primary-stack.md) | Python 3.11+ as the primary stack | Accepted | 2026-08-08 |
| [0005](0005-ml-classifier-now-lora-later.md) | ML classifier now, LoRA explainer later | Accepted | 2026-08-08 |

New ADRs should copy [`0000-template.md`](0000-template.md), take the next number in
sequence, and be linked into the table above.
