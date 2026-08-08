"""Rewind: an open-source flight recorder and time-travel debugger for AI agents.

Record an agent run's nondeterministic boundaries, then replay it bit-for-bit offline
with zero API calls. This is the Phase-0 walking skeleton; the public surface will grow.
"""

from __future__ import annotations

from .boundary import Boundary, Cassette, Divergence, Session
from .replay import VerifyResult, record, replay_once, verify
from .store import RunStore, RunSummary

__version__ = "0.0.0"
__all__ = [
    "Boundary",
    "Cassette",
    "Divergence",
    "RunStore",
    "RunSummary",
    "Session",
    "VerifyResult",
    "__version__",
    "record",
    "replay_once",
    "verify",
]
