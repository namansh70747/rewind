# ADR-0009: Local alpha with explicit-mock counterfactuals

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

The capture/replay core exists, but the roadmap-facing README did not expose a
complete demonstration. A credible local release needs a reproducible investigation
and honest boundaries without pretending the fleet/ML research has already shipped.

## Decision

Build on ADR-0006's separation between recorded playback and exploratory forks.
Keep existing BLAKE2b/zlib recordings compatible. Add exact-prefix counterfactual
execution that substitutes one response and requires explicit mocks for every new
boundary afterward. Preserve parent fingerprint and intervention index. Do not allow
live external producers in this initial fork API.

Provide a static HTML investigation artifact with embedded escaped data rather than
a server or frontend build dependency. State inspection uses explicit `state` events
and prefix evidence, not Python heap restoration. Synthetic teaching services are
labeled, while actual replay/evaluation results come from execution.

Add a best-effort Python socket guard to replay, explicitly distinguish it from an
OS sandbox, and verify integrity before execution. Preserve ABI-compatible optional
cassette metadata in an additive SQLite table and version the portable JSON envelope.

## Consequences

The demo is reproducible on a laptop with no provider keys and no real side effects
through mediated tools. Tests can prove the transition from failure to recovery.
Counterfactual continuations are hypotheses dependent on the supplied mocks, not
predictions of future production behavior. Full concurrent replay, fleet ML and
framework adapters remain separate work. This proposal requires maintainer review.
