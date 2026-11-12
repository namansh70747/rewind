"""Counterfactual execution: exact prefix, one intervention, explicit safe mocks."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from .boundary import Boundary, Cassette, Divergence, Session, canon, chain_link
from .integrity import validate
from .offline import NetworkBlocked, offline_guard
from .redaction import redact

if TYPE_CHECKING:
    from .replay import Run

Mock = Callable[[Any], Any]


class ForkSession(Session):
    """Never invoke a boundary's real producer, even after the intervention."""

    def __init__(
        self, parent: Cassette, at: int, value: Any, mocks: Mapping[tuple[str, str], Mock]
    ) -> None:
        validate(parent)
        if parent.metadata.get("concurrent"):
            raise ValueError("concurrent forks are not supported; serialize this scenario")
        if parent.metadata.get("replayable") is False:
            raise ValueError("trace-only evidence cannot be forked")
        if not 0 <= at < len(parent.boundaries):
            raise ValueError("fork index is outside the recording")
        super().__init__("replay", parent)
        self.at = at
        self.value = copy.deepcopy(value)
        self.mocks = mocks

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        index = len(self.boundaries)
        if index < self.at:
            result = super().mediate(kind, key, request, produce)
            self.boundaries.append(copy.deepcopy(self._recorded[index]))
            return result
        if index == self.at:
            original = self._recorded[index]
            if canon([kind, key, request]) != canon(
                [original.kind, original.key, original.request]
            ):
                raise Divergence(index, "fork target input differs from parent")
            result = copy.deepcopy(self.value)
        else:
            mock = self.mocks.get((kind, key))
            if mock is None:
                raise Divergence(index, f"safe fork needs an explicit mock for {kind}/{key}")
            result = mock(copy.deepcopy(request))
        result = redact(result)
        self.chain = chain_link(
            self.chain, canon([kind, key, request]), canon(result), self.algorithm
        )
        self.boundaries.append(
            Boundary(index, kind, key, copy.deepcopy(request), copy.deepcopy(result), self.chain)
        )
        return copy.deepcopy(result)


def fork_run(
    parent: Cassette,
    run: Run,
    *,
    at: int,
    value: Any,
    mocks: Mapping[tuple[str, str], Mock] | None = None,
) -> Cassette:
    """Execute agent logic with a changed value, failing closed on unspecified I/O.

    The callback must route effects through Session. This is not a filesystem or
    subprocess sandbox. Only run trusted agents; external tool producers never run.
    """
    session = ForkSession(parent, at, value, mocks or {})
    with offline_guard() as audit:
        output = run(session, None)
    if audit.blocked_operations:
        raise NetworkBlocked("fork attempted unmediated network I/O, even if the error was caught")
    if len(session.boundaries) <= at:
        raise Divergence(len(session.boundaries), "agent stopped before fork target")
    return Cassette(
        session.boundaries,
        session.chain,
        output,
        parent.provider,
        parent.model,
        {
            **parent.metadata,
            "counterfactual": True,
            "parent_fingerprint": parent.fingerprint,
            "fork_at": at,
            "continuation_policy": "explicit-mocks-only",
        },
        parent.chain_algorithm,
    )


async def afork_run(
    parent: Cassette,
    run: Callable[[Session], Awaitable[str]],
    *,
    at: int,
    value: Any,
    mocks: Mapping[tuple[str, str], Mock] | None = None,
) -> Cassette:
    """Await a serialized async agent; every continuation boundary needs a mock.

    Async producers are never awaited. This supports LangGraph's async event loop
    without nesting asyncio.run() or allowing network I/O during replay.
    """
    session = ForkSession(parent, at, value, mocks or {})
    with offline_guard() as audit:
        output = await run(session)
    if audit.blocked_operations:
        raise NetworkBlocked("fork attempted unmediated network I/O, even if the error was caught")
    if len(session.boundaries) <= at:
        raise Divergence(len(session.boundaries), "agent stopped before fork target")
    return Cassette(
        session.boundaries,
        session.chain,
        output,
        parent.provider,
        parent.model,
        {
            **parent.metadata,
            "counterfactual": True,
            "parent_fingerprint": parent.fingerprint,
            "fork_at": at,
            "continuation_policy": "explicit-mocks-only",
        },
        parent.chain_algorithm,
    )
