"""Best-effort Python socket guard; not an OS sandbox or protection from hostile code."""

from __future__ import annotations

import socket
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Iterator


class NetworkBlocked(RuntimeError):
    """An unrecorded network path attempted I/O during replay."""


@dataclass
class NetworkAudit:
    blocked_operations: list[str] = field(default_factory=list)


_audit: ContextVar[NetworkAudit | None] = ContextVar("rewind_network_audit", default=None)
_SOCKET_ORIGINALS = {
    name: getattr(socket.socket, name)
    for name in ("connect", "connect_ex", "sendto", "send", "sendall")
}
_DNS_ORIGINAL = socket.getaddrinfo


def _blocked(*args: Any, **kwargs: Any) -> Any:
    raise NetworkBlocked("offline replay blocked an unrecorded socket operation")


@contextmanager
def authorized_network() -> Iterator[None]:
    """Internal trusted-policy scope; caller must already authorize this producer."""
    with ExitStack() as stack:
        for name, original in _SOCKET_ORIGINALS.items():
            stack.enter_context(patch.object(socket.socket, name, original))
        stack.enter_context(patch.object(socket, "getaddrinfo", _DNS_ORIGINAL))
        yield


@contextmanager
def offline_guard(audit: NetworkAudit | None = None) -> Iterator[NetworkAudit]:
    """Best-effort Python socket guard with observed blocked-operation evidence.

    Not an OS sandbox. Native extensions, cached aliases and subprocesses are
    outside the guarantee. Use in an isolated, trusted agent process.
    """
    report = audit or _audit.get() or NetworkAudit()
    token = _audit.set(report)

    def make_blocker(name: str) -> Any:
        def blocked(*args: Any, **kwargs: Any) -> Any:
            report.blocked_operations.append(name)
            return _blocked(*args, **kwargs)

        return blocked

    try:
        with ExitStack() as stack:
            for name in _SOCKET_ORIGINALS:
                stack.enter_context(patch.object(socket.socket, name, make_blocker(name)))
            stack.enter_context(patch.object(socket, "getaddrinfo", make_blocker("getaddrinfo")))
            yield report
    finally:
        _audit.reset(token)
