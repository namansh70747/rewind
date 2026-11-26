"""Best-effort context-aware Python socket guard; not an OS sandbox."""

from __future__ import annotations

import socket
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
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
_authorized: ContextVar[bool] = ContextVar("rewind_authorized_network", default=False)
_SOCKET_ORIGINALS = {
    name: getattr(socket.socket, name)
    for name in ("connect", "connect_ex", "sendto", "send", "sendall")
}
_DNS_ORIGINAL = socket.getaddrinfo
_lock = RLock()
_active: dict[int, tuple[NetworkAudit, int]] = {}
_stack: ExitStack | None = None


def _blocked(*args: Any, **kwargs: Any) -> Any:
    raise NetworkBlocked("offline replay blocked an unrecorded socket operation")


def _make_blocker(name: str) -> Any:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        if _authorized.get():
            original = _DNS_ORIGINAL if name == "getaddrinfo" else _SOCKET_ORIGINALS[name]
            return original(*args, **kwargs)
        current = _audit.get()
        with _lock:
            # Unbound child threads cannot silently escape the process-wide guard.
            reports = [current] if current is not None else [r for r, _ in _active.values()]
            for report in reports:
                report.blocked_operations.append(name)
        return _blocked(*args, **kwargs)

    return blocked


@contextmanager
def authorized_network() -> Iterator[None]:
    """Trusted policy authorization for this context only; never unpatch other threads."""
    token = _authorized.set(True)
    try:
        yield
    finally:
        _authorized.reset(token)


@contextmanager
def offline_guard(audit: NetworkAudit | None = None) -> Iterator[NetworkAudit]:
    """Reference-count process patches; attribute attempts to the caller's context.

    Concurrent guards share one patch lifetime, so one replay exiting cannot
    restore sockets underneath another. Native code/cached aliases/subprocesses
    remain outside this best-effort trusted-code contract.
    """
    global _stack
    report = audit or _audit.get() or NetworkAudit()
    token = _audit.set(report)
    authorization = _authorized.set(False)
    identity = id(report)
    try:
        with _lock:
            if not _active:
                stack = ExitStack()
                try:
                    for name in _SOCKET_ORIGINALS:
                        stack.enter_context(patch.object(socket.socket, name, _make_blocker(name)))
                    stack.enter_context(
                        patch.object(socket, "getaddrinfo", _make_blocker("getaddrinfo"))
                    )
                except BaseException:
                    stack.close()
                    raise
                _stack = stack
            count = _active.get(identity, (report, 0))[1]
            _active[identity] = (report, count + 1)
        try:
            yield report
        finally:
            with _lock:
                _, count = _active[identity]
                if count == 1:
                    del _active[identity]
                else:
                    _active[identity] = (report, count - 1)
                if not _active and _stack is not None:
                    _stack.close()
                    _stack = None
    finally:
        _authorized.reset(authorization)
        _audit.reset(token)
