"""Opt-in replay pacing for captured decoded HTTP chunks; fast playback is default."""

from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_TIMING_SCALE: ContextVar[float] = ContextVar("rewind_stream_timing", default=0.0)


@contextmanager
def stream_playback_timing(scale: float = 1.0) -> Iterator[None]:
    """1 reproduces recorded relative offsets, 0 disables pacing, .5 is twice as fast.

    Pacing uses monotonic deadlines. Scheduler precision is best effort. Recordings
    containing a scaled pause over 30 seconds fail rather than block unexpectedly.
    """
    if not math.isfinite(scale) or not 0 <= scale <= 100:
        raise ValueError("timing scale must be finite and between 0 and 100")
    token = _TIMING_SCALE.set(scale)
    try:
        yield
    finally:
        _TIMING_SCALE.reset(token)


def chunk_deadlines(offsets: object, count: int, scale: float) -> list[float]:
    if not scale:
        return [0.0] * count
    if not isinstance(offsets, list) or len(offsets) != count:
        raise ValueError("timed replay requires one offset per chunk")
    previous = 0
    result = []
    for value in offsets:
        if type(value) is not int or value < previous:
            raise ValueError("chunk offsets must be nonnegative monotonic integers")
        seconds = value * scale / 1_000_000_000
        if (value - previous) * scale / 1_000_000_000 > 30:
            raise ValueError("recorded chunk pause exceeds 30-second playback safety limit")
        previous = value
        result.append(seconds)
    return result
