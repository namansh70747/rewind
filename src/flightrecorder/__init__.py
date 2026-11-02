"""Rewind: an open-source flight recorder and time-travel debugger for AI agents.

Record an agent run's nondeterministic boundaries, then replay it bit-for-bit offline
with zero API calls. Local alpha; see the README for supported capture boundaries and limitations.
"""

from __future__ import annotations

from .bisect import BisectResult, first_divergence
from .boundary import Boundary, Cassette, Divergence, Session
from .capture import Capture, capture, replay_run, verify_run
from .fork import fork_run
from .inspection import state_at
from .integrity import validate
from .redaction import redact, redact_text
from .replay import VerifyResult, record, replay_once, verify
from .store import RunStore, RunSummary
from .tools import tool

__version__ = "0.1.0"
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
    "capture",
    "first_divergence",
    "fork_run",
    "record",
    "redact",
    "redact_text",
    "replay_once",
    "replay_run",
    "state_at",
    "tool",
    "validate",
    "verify",
    "verify_run",
]
