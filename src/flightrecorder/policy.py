"""Explicit continuation policy. Live means authorized by the calling application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .fork import ForkSession
from .offline import authorized_network

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class SideEffectPolicy:
    read_only: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    live_allowlist: frozenset[tuple[str, str]] = field(default_factory=frozenset)

    def permits(self, kind: str, key: str) -> bool:
        # Classification alone never grants live execution; opt-in is required.
        return (kind, key) in self.live_allowlist


class PolicyForkSession(ForkSession):
    """A separate explicit live mode; replay/default forks remain strictly offline.

    Applications must enforce user authorization before populating live_allowlist.
    A supplied mock takes precedence. No implicit live HTTP/model continuation.
    """

    policy: SideEffectPolicy = SideEffectPolicy()

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        if (
            len(self.boundaries) > self.at
            and (kind, key) not in self.mocks
            and self.policy.permits(kind, key)
        ):
            temporary = dict(self.mocks)

            def allowed(_: Any) -> Any:
                with authorized_network():
                    return produce()

            temporary[(kind, key)] = allowed
            original = self.mocks
            self.mocks = temporary
            try:
                return super().mediate(kind, key, request, produce)
            finally:
                self.mocks = original
        return super().mediate(kind, key, request, produce)


def fork_with_policy(
    parent: Any, run: Any, *, at: int, value: Any, mocks: Any, policy: SideEffectPolicy
) -> Any:
    """Explicit application-authorized live continuation, with quarantined provenance.

    Network guarding is retained outside allowlisted producers. This is a trusted
    application API, not a security boundary against arbitrary Python code.
    """
    from .boundary import Cassette, Divergence
    from .offline import NetworkBlocked, offline_guard

    session = PolicyForkSession(parent, at, value, mocks)
    session.policy = policy
    with offline_guard() as audit:
        output = run(session, None)
    if audit.blocked_operations:
        raise NetworkBlocked("fork attempted unmediated network I/O, even if the error was caught")
    if len(session.boundaries) <= at:
        raise Divergence(len(session.boundaries), "fork target was not reached")
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
            "continuation_policy": "explicit-allowlist",
            "live_allowlist": [list(item) for item in sorted(policy.live_allowlist)],
        },
        parent.chain_algorithm,
    )


def policy_from_manifest(data: Any) -> SideEffectPolicy:
    """Parse an explicit manifest; classification alone never grants live execution."""
    if not isinstance(data, dict) or set(data) != {"version", "tools"} or data["version"] != 1:
        raise ValueError("policy must contain version=1 and tools")
    if not isinstance(data["tools"], list):
        raise ValueError("policy tools must be a list")
    seen: set[tuple[str, str]] = set()
    read_only: set[tuple[str, str]] = set()
    live: set[tuple[str, str]] = set()
    for row in data["tools"]:
        if not isinstance(row, dict) or set(row) != {"kind", "key", "mutating", "live"}:
            raise ValueError("each policy entry needs kind, key, mutating and live")
        if not all(isinstance(row[k], str) and row[k].strip() for k in ("kind", "key")):
            raise ValueError("kind and key must be non-empty strings")
        if type(row["mutating"]) is not bool or type(row["live"]) is not bool:
            raise ValueError("mutating and live must be JSON booleans")
        identity = (row["kind"], row["key"])
        if identity in seen:
            raise ValueError("duplicate policy entry")
        seen.add(identity)
        if not row["mutating"]:
            read_only.add(identity)
        if row["live"]:
            live.add(identity)
    return SideEffectPolicy(frozenset(read_only), frozenset(live))
