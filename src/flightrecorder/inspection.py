"""Timeline inspection and reproducible fleet similarity (no external models)."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .boundary import Cassette


def state_at(cassette: Cassette, at: int) -> dict[str, Any]:
    """Return only evidence available at a boundary; never leak future steps.

    This is boundary-observable state, not a Python heap/process snapshot.
    Agents can emit explicit `state` boundaries for application snapshots.
    """
    from .snapshots import SnapshotIndex

    index = SnapshotIndex(cassette)
    return {**index.at(at), "boundary": asdict(index.cassette.boundaries[at])}


def features(cassette: Cassette) -> Counter[str]:
    """Interpretable event features, intentionally excluding prompts and personal text."""
    values: Counter[str] = Counter()
    for b in cassette.boundaries:
        values[f"kind:{b.kind}"] += 1
        values[f"boundary:{b.kind}:{b.key}"] += 1
        if isinstance(b.response, dict):
            for name in ("status", "error", "tool"):
                if name in b.response:
                    values[f"{name}:{b.response[name]}"] += 2
    return values


def similarity(a: Cassette, b: Cassette) -> float:
    """Cosine similarity on event-count vectors, not a learned root-cause prediction."""
    left, right = features(a), features(b)
    norm = math.sqrt(sum(v * v for v in left.values()) * sum(v * v for v in right.values()))
    return sum(value * right[key] for key, value in left.items()) / norm if norm else 0.0
