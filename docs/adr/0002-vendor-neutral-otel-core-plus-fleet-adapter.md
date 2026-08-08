# ADR-0002: Vendor-neutral OpenTelemetry core plus a first-class fleet adapter

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Naman Sharma (@namansh70747)

## Context

Rewind must instrument real agents to record their boundary reads. There is a tension
between two goals:

1. **Reach** — Rewind should work with *any* agent (OpenAI, Anthropic, LangGraph, and
   frameworks not yet invented), or it becomes a niche tool tied to one ecosystem.
2. **Depth** — the fleet/ML features (P4) need a large, real corpus of runs to be
   worth anything, and the author already operates a substantial MCP tool fleet
   (672 tools across 10 providers) that is the ideal proving ground.

The OpenTelemetry **GenAI semantic conventions** exist as an emerging, vendor-neutral
standard for describing agent/LLM runs structurally (spans, causal relationships), and
have free ecosystem viewers (Jaeger, Tempo, Perfetto). But OTel content capture is
opt-in and truncated, so it cannot by itself hold the payloads needed for faithful
replay.

We must decide where the core abstraction lives, and how much to specialize toward the
author's own fleet.

## Decision

**We will build the core on the OpenTelemetry GenAI conventions as a vendor-neutral
structural/index layer, and additionally ship a first-class adapter for the author's
MCP fleet.**

Concretely:

- The **capture and replay core is framework-agnostic**, driven by `wrapt`-based
  interception and keyed on OTel GenAI spans for structure and causal ordering. Any
  unmodified OpenAI / Anthropic / LangGraph agent can be recorded and replayed.
- OTel provides **structure and a free viewing path** (export to Jaeger/Tempo), but
  Rewind **stores the real payload bytes itself**, content-addressed, because OTel
  content capture is opt-in/truncated and unfit for faithful replay.
- On top of the neutral core, a **first-class MCP fleet adapter** instruments the
  author's fleet as the primary real-world corpus for the P4 fleet/ML work.

## Consequences

**Easier**

- Broad reach from day one: adopters aren't locked to one framework, and we ride a
  standard rather than inventing a bespoke trace format.
- Free structural visualization via existing OTel tooling, so we don't have to build a
  general trace viewer to be useful early.
- A guaranteed, large, realistic dataset (the fleet) to develop and validate the ML
  layer against, instead of waiting for external users.

**Harder / costs**

- We maintain **two things**: the neutral core *and* the fleet adapter, and must keep
  the adapter from leaking fleet-specific assumptions into the core.
- We depend on an **evolving** standard (OTel GenAI conventions are still maturing),
  so we must track and absorb changes.
- Because OTel can't hold payloads, we must run our **own** content-addressed blob
  store alongside the OTel structure — two representations of one run to keep in sync.

## Alternatives Considered

- **Framework-agnostic core only (no fleet adapter).** Maximizes neutrality but leaves
  us without a rich, real corpus to build the fleet/ML features on, and forgoes the
  author's best available proving ground. Rejected: depth matters for P4, and the
  adapter costs little relative to its value.

- **Build solely on the MCP fleet.** Fastest path to a deep, working end-to-end
  demonstration on real data, but produces a tool that only works for one fleet and
  cannot be adopted by anyone else — fatal for an open-source project whose thesis is
  general. Rejected: it sacrifices the reach that makes the project matter.
