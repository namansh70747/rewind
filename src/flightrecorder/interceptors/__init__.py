"""Boundary interceptors — where Rewind hooks the nondeterministic world.

Phase 0 ships the HTTP transport interceptor (ADR-0007); clock/uuid/rng shims live on
:class:`flightrecorder.boundary.Session`. Later phases add broad ``wrapt``-based hooks and
an OpenTelemetry span processor.
"""

from __future__ import annotations

from .transport import RecordingTransport

__all__ = ["RecordingTransport"]
