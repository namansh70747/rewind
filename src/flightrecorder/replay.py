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
from .strict import strict_guard

Run = Callable[[Session, httpx.BaseTransport | None], str]


def record(
    run: Run, inner: httpx.BaseTransport, *, provider: str = "", model: str = ""
) -> Cassette:
    """Run once against the real (or mock) world, capturing every boundary."""
    session = Session("record")
    output = run(session, inner)
    return Cassette(
        boundaries=session.boundaries,
        fingerprint=session.chain,
        final_output=output,
        provider=provider,
        model=model,
    )


def replay_once(cassette: Cassette, run: Run, *, strict: bool = False) -> tuple[str, str]:
    """Re-run the agent serving recorded values; returns (output, fingerprint).

    ``strict`` refuses uncaptured ``time`` / ``random`` / ``uuid`` / ``os.urandom`` reads
    in agent code (see :func:`flightrecorder.strict.strict_guard`).
    """
    session = Session("replay", cassette)
    if strict:
        with strict_guard(session):
            output = run(session, None)  # inner=None -> network kill-switch
    else:
        output = run(session, None)  # inner=None -> network kill-switch
    session.assert_fully_consumed()
    return output, session.chain


@dataclass
class VerifyResult:
    passed: bool
    runs: int
    unique_outputs: int
    unique_fingerprints: int
    detail: str

    @property
    def verdict(self) -> str:
        """First-class replay line: ``replay verified ✓`` or ``replay verified ✗``."""
        return "replay verified ✓" if self.passed else "replay verified ✗"

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"{self.verdict}\n"
            f"{verdict}  replays={self.runs}  distinct_outputs={self.unique_outputs}  "
            f"distinct_fingerprints={self.unique_fingerprints}\n  {self.detail}"
        )


def verify(cassette: Cassette, run: Run, n: int = 50, *, strict: bool = False) -> VerifyResult:
    """Replay ``n`` times; PASS iff every replay is byte-identical to the recording."""
    outputs: set[str] = set()
    fingerprints: set[str] = set()
    for i in range(n):
        try:
            output, fingerprint = replay_once(cassette, run, strict=strict)
        except Divergence as exc:
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
