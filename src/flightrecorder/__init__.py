"""Rewind: an open-source flight recorder and time-travel debugger for AI agents.

Record an agent run's nondeterministic boundaries, then replay it bit-for-bit offline
with zero API calls. This is the Phase-0 walking skeleton; the public surface will grow.
"""

from __future__ import annotations

from .bisect import BisectResult, first_divergence
from .boundary import Boundary, Cassette, Divergence, Session
from .capture import Capture, active_session, capture, replay_run, verify_run
from .redaction import redact, redact_text
from .replay import VerifyResult, record, replay_once, verify
from .store import RunStore, RunSummary
from .tool import tool

__version__ = "0.0.0"
__all__ = [
    "BisectResult",
    "Boundary",
    "Capture",
    "Cassette",
    "Divergence",
    "RunStore",
    "RunSummary",
    "Session",
    "VerifyResult",
    "__version__",
    "active_session",
    "capture",
    "first_divergence",
    "record",
    "redact",
    "redact_text",
    "replay_once",
    "replay_run",
    "tool",
    "verify",
    "verify_run",
]
