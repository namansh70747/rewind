"""Spike A — the bit-exact playback go/no-go (Rewind Week 1).

THROWAWAY spike code. It exists to answer one question before we build the real
engine: *can a recorded agent run be replayed bit-for-bit, offline, with zero API
calls, and can we prove it with a divergence oracle that fails loud?*

This is deliberately NOT the real ``flightrecorder`` package — it is the smallest
harness that exercises the core thesis (see docs/plan/risks-and-spikes.md, Spike A,
and ADR-0006 / ADR-0007).
"""

from __future__ import annotations

__all__ = ["__doc__"]
