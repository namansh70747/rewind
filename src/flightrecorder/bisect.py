"""Auto-bisect v1 — find the first diverging decision between two recordings.

Given a passing run and a failing run of the same task, the first point where they diverge
is the root-cause candidate. v1 walks both boundary sequences and returns the first index
whose recorded content differs, classifying it:

* **same input → different output** — the *decision* diverged here (e.g. sampling, a model
  change): the request was identical but the response differed.
* **different input → different output** — an *upstream* value diverged; the real cause is
  earlier, so keep walking back.

This is the step-aligned bisect from ``docs/plan/algorithms-and-math.md`` (§1/§3). It
assumes the two runs share a prefix; sequence alignment for insert/delete cases
(Needleman-Wunsch / DTW) is a later phase. See ADR-0006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .boundary import canon

if TYPE_CHECKING:
    from .boundary import Boundary, Cassette


@dataclass
class BisectResult:
    """Where (and how) two recordings first diverge."""

    diverged: bool
    index: int | None
    reason: str
    a: Boundary | None = None
    b: Boundary | None = None

    def __str__(self) -> str:
        if not self.diverged:
            return "no divergence — the two runs are identical"
        return f"first divergence at boundary #{self.index}: {self.reason}"


def _identity(boundary: Boundary) -> bytes:
    return canon([boundary.kind, boundary.key, boundary.request, boundary.response])


def _inputs(boundary: Boundary) -> bytes:
    return canon([boundary.kind, boundary.key, boundary.request])


def first_divergence(a: Cassette, b: Cassette) -> BisectResult:
    """Return the first boundary where recordings ``a`` and ``b`` diverge."""
    common = min(len(a.boundaries), len(b.boundaries))
    for i in range(common):
        ba, bb = a.boundaries[i], b.boundaries[i]
        if _identity(ba) != _identity(bb):
            same_input = _inputs(ba) == _inputs(bb)
            reason = (
                "same input → different output (the decision/response diverged here)"
                if same_input
                else "different input → different output (an upstream value diverged; look earlier)"
            )
            return BisectResult(True, i, reason, ba, bb)

    if len(a.boundaries) != len(b.boundaries):
        longer = "a" if len(a.boundaries) > len(b.boundaries) else "b"
        next_a = a.boundaries[common] if common < len(a.boundaries) else None
        next_b = b.boundaries[common] if common < len(b.boundaries) else None
        reason = (
            f"runs share a {common}-step prefix, then run {longer} takes an extra step "
            f"({len(a.boundaries)} vs {len(b.boundaries)} boundaries)"
        )
        return BisectResult(True, common, reason, next_a, next_b)

    return BisectResult(False, None, "identical")
