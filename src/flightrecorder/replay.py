"""Record / replay / verify orchestration.

* ``record`` runs the agent once against the real world, capturing every boundary.
* ``replay_once`` re-runs the agent serving recorded values (network kill-switch on).
* ``verify`` replays N times and confirms every replay is byte-identical to the recording.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .boundary import Cassette, Divergence, Session
from .integrity import validate
from .offline import NetworkBlocked, offline_guard

Run = Callable[[Session, httpx.BaseTransport | None], str]


def record(
    run: Run,
    inner: httpx.BaseTransport | None = None,
    *,
    provider: str = "",
    model: str = "",
    concurrent: bool = False,
) -> Cassette:
    """Run once against the real (or mock) world, capturing every boundary."""
    from .concurrency import ConcurrentSession

    session = ConcurrentSession("record") if concurrent else Session("record")
    output = run(session, inner)
    return Cassette(
        boundaries=session.boundaries,
        fingerprint=session.chain,
        final_output=output,
        provider=provider,
        model=model,
        metadata={"concurrent": concurrent},
    )


def replay_once(cassette: Cassette, run: Run) -> tuple[str, str]:
    """Re-run the agent serving recorded values; returns (output, fingerprint)."""
    validate(cassette)
    if cassette.metadata.get("replayable") is False:
        raise Divergence(0, "trace-only evidence cannot be executed as a replay")
    from .concurrency import ConcurrentSession

    session = (
        ConcurrentSession("replay", cassette)
        if cassette.metadata.get("concurrent")
        else Session("replay", cassette)
    )
    with offline_guard() as audit:
        output = run(session, None)  # inner=None -> network kill-switch
    if audit.blocked_operations:
        raise NetworkBlocked(
            "agent attempted unrecorded network I/O, even though it caught the error"
        )
    session.assert_fully_consumed()
    return output, session.chain


@dataclass
class VerifyResult:
    passed: bool
    runs: int
    unique_outputs: int
    unique_fingerprints: int
    detail: str

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"{verdict}  replays={self.runs}  distinct_outputs={self.unique_outputs}  "
            f"distinct_fingerprints={self.unique_fingerprints}\n  {self.detail}"
        )


def verify(cassette: Cassette, run: Run, n: int = 50) -> VerifyResult:
    """Replay ``n`` times; PASS iff every replay is byte-identical to the recording."""
    if n < 1:
        raise ValueError("number of replays must be at least 1")
    outputs: set[str] = set()
    fingerprints: set[str] = set()
    for i in range(n):
        try:
            output, fingerprint = replay_once(cassette, run)
        except (Divergence, NetworkBlocked) as exc:
            return VerifyResult(False, i + 1, len(outputs), len(fingerprints), f"replay {i}: {exc}")
        outputs.add(output)
        fingerprints.add(fingerprint)

    passed = outputs == {cassette.final_output} and fingerprints == {cassette.fingerprint}
    detail = (
        "all replays byte-identical to the recording; hash-chain matches"
        if passed
        else (
            f"MISMATCH — expected 1 output/fingerprint matching the recording, got "
            f"{len(outputs)} outputs / {len(fingerprints)} fingerprints"
        )
    )
    return VerifyResult(passed, n, len(outputs), len(fingerprints), detail)
