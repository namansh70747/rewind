"""Global capture of an *unmodified* agent (Phase 1, advances #16).

The walking skeleton records agents that use a `Session`-wired client. This adds the
headline capability: record code that just uses plain ``httpx`` — no ``flightrecorder``
imports in the agent itself.

    with capture(store, provider="nvidia") as cap:
        run_my_unmodified_agent()        # uses httpx.Client() normally
    print(cap.run_id)

    verify_run(cap.cassette, run_my_unmodified_agent)   # replay it, bit-exact, offline

**How:** inside the block we monkeypatch ``httpx.Client.__init__`` so every client's
transport is wrapped with a :class:`RecordingTransport` bound to the active session (an
approach borrowed from VCR.py). Replay serves recorded responses with the network
kill-switch on.

**Scope (this increment):** synchronous ``httpx.Client`` only, and only the **HTTP**
boundary is captured globally. Non-HTTP nondeterminism in an unmodified agent (wall-clock,
``uuid``, RNG) is *not* auto-captured yet — if it affects the run, the divergence oracle
will flag it loudly on replay rather than lie. (Agents that need those captured can use the
``Session`` shims, as the bundled example agent does.) Global clock/uuid/rng shims, async,
and a ``fr record -- python agent.py`` subprocess wrapper are follow-ups.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from .boundary import Cassette, Divergence, Session
from .interceptors.transport import RecordingTransport
from .replay import VerifyResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .store import RunStore

_active_session: ContextVar[Session | None] = ContextVar("flightrecorder_session", default=None)
_orig_client_init = httpx.Client.__init__
#: Nesting depth for the process-global ``Client.__init__`` patch. ContextVar correctly
#: stacks sessions, but restoring ``__init__`` on the first nested exit would unpatch the
#: outer ``capture()`` / ``replay_run()`` still in flight.
_patch_depth = 0


def _wrap_transport(
    session: Session, transport: httpx.BaseTransport | None
) -> httpx.BaseTransport | None:
    """Wrap a transport (or mount entry) with ``RecordingTransport`` if needed."""
    if transport is None or isinstance(transport, RecordingTransport):
        return transport
    return RecordingTransport(session, inner=transport)


def _patched_client_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
    _orig_client_init(self, *args, **kwargs)
    session = _active_session.get()
    if session is None:
        return
    # httpx routes via mounts first (proxies); wrapping only ``_transport`` misses those.
    wrapped = _wrap_transport(session, self._transport)
    if wrapped is not None:
        self._transport = wrapped
    self._mounts = {
        pattern: _wrap_transport(session, transport) for pattern, transport in self._mounts.items()
    }


@contextlib.contextmanager
def _patched(session: Session) -> Iterator[None]:
    """Install the httpx patch + bind the active session for the duration of the block."""
    global _patch_depth
    token = _active_session.set(session)
    if _patch_depth == 0:
        httpx.Client.__init__ = _patched_client_init  # type: ignore[method-assign]
    _patch_depth += 1
    try:
        yield
    finally:
        _patch_depth -= 1
        if _patch_depth == 0:
            httpx.Client.__init__ = _orig_client_init  # type: ignore[method-assign]
        _active_session.reset(token)


@dataclass
class Capture:
    """Handle returned by :func:`capture`; ``cassette`` / ``run_id`` are set on block exit."""

    session: Session
    cassette: Cassette | None = None
    run_id: str | None = None


@contextlib.contextmanager
def capture(
    store: RunStore | None = None, *, provider: str = "", model: str = ""
) -> Iterator[Capture]:
    """Record every ``httpx`` call made by unmodified code inside the block."""
    session = Session("record")
    handle = Capture(session=session)
    with _patched(session):
        yield handle
    handle.cassette = Cassette(
        boundaries=session.boundaries,
        fingerprint=session.chain,
        final_output="",
        provider=provider,
        model=model,
    )
    if store is not None:
        handle.run_id = store.save(handle.cassette)


def replay_run(cassette: Cassette, fn: Callable[[], Any]) -> str:
    """Re-run an unmodified callable serving recorded values; returns the replay fingerprint."""
    session = Session("replay", cassette)
    with _patched(session):
        fn()
    session.assert_fully_consumed()
    return session.chain


def verify_run(cassette: Cassette, fn: Callable[[], Any], n: int = 50) -> VerifyResult:
    """Replay an unmodified callable ``n`` times; PASS iff every fingerprint matches."""
    fingerprints: set[str] = set()
    for i in range(n):
        try:
            fingerprints.add(replay_run(cassette, fn))
        except Divergence as exc:
            return VerifyResult(False, i + 1, 0, len(fingerprints), f"replay {i}: {exc}")
    passed = fingerprints == {cassette.fingerprint}
    detail = (
        "all replays match the recorded fingerprint (bit-exact)"
        if passed
        else f"MISMATCH — {len(fingerprints)} distinct fingerprints, expected exactly 1"
    )
    return VerifyResult(passed, n, 0, len(fingerprints), detail)
