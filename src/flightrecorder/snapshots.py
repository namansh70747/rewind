"""Copy-on-write boundary state checkpoints with sqrt(N) bounded suffix scans."""

from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Any

from .integrity import validate

if TYPE_CHECKING:
    from .boundary import Cassette


class SnapshotIndex:
    """Immutable indexed evidence, not arbitrary process memory.

    Checkpoints shallow-copy maps while payloads are shared internally. Exposed
    values are deep copies. Build once O(N), query <= interval event applications.
    """

    def __init__(self, cassette: Cassette, interval: int | None = None) -> None:
        validate(cassette)
        self.cassette = copy.deepcopy(cassette)
        self.interval = (
            max(1, math.isqrt(len(cassette.boundaries))) if interval is None else interval
        )
        if type(self.interval) is not int or self.interval < 1:
            raise ValueError("snapshot interval must be a positive integer")
        self.checkpoints: dict[int, tuple[dict[str, Any], Any]] = {}
        observed: dict[str, Any] = {}
        state: Any = None
        for b in self.cassette.boundaries:
            observed[f"{b.kind}:{b.key}"] = b.response
            if b.kind == "state":
                state = b.response
            if b.seq % self.interval == 0:
                self.checkpoints[b.seq] = (observed.copy(), state)

    def at(self, at: int) -> dict[str, Any]:
        if not 0 <= at < len(self.cassette.boundaries):
            raise ValueError("boundary index is outside recording")
        start = at // self.interval * self.interval
        observed, state = self.checkpoints[start]
        observed = observed.copy()
        for b in self.cassette.boundaries[start + 1 : at + 1]:
            observed[f"{b.kind}:{b.key}"] = b.response
            if b.kind == "state":
                state = b.response
        return copy.deepcopy(
            {
                "at": at,
                "checkpoint": start,
                "replayed_events": at - start,
                "observed": observed,
                "agent_snapshot": state,
                "final_output": self.cassette.final_output
                if at == len(self.cassette.boundaries) - 1
                else None,
            }
        )
