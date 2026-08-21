"""The spine: a ``Session`` that mediates every nondeterministic boundary.

An agent run is a sequence of **boundary reads** — every value the agent gets from the
outside world (an LLM HTTP response, the clock, a UUID, an RNG draw). ``RECORD`` calls
the real world and logs the value; ``REPLAY`` serves the recorded value, never calls out,
and verifies a BLAKE2b **hash-chain** link by link, raising :class:`Divergence` — loud and
localized — at the first mismatch.

See ADR-0006 (replay is playback, not re-execution) and ADR-0008 (our own recording
schema). HTTP capture lives in :mod:`flightrecorder.interceptors.transport` (ADR-0007);
clock/uuid/rng are shimmed here.

**Phase-0 provisional format (not frozen).** The hash-chain uses stdlib ``blake2b`` to keep
the walking skeleton dependency-free; the ADR-frozen algorithm will be **BLAKE3**
(``docs/plan/algorithms-and-math.md`` §1). Because the chain algorithm is part of the
recording identity, recordings made now are not guaranteed to survive the switch — the
on-disk recording format is not yet frozen (that happens ~Week 8, per the plan).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

Mode = Literal["record", "replay"]

#: 32 zero bytes, hex-encoded — the genesis link of every run's hash-chain.
GENESIS = "00" * 32


def _unreachable() -> Any:  # pragma: no cover - only wired into the replay path, never called
    raise RuntimeError("boundary producer must not run during replay")


class Divergence(Exception):
    """Raised the instant replay stops matching the recording, naming the boundary."""

    def __init__(self, seq: int, message: str) -> None:
        self.seq = seq
        super().__init__(f"boundary #{seq}: {message}")


def canon(obj: Any) -> bytes:
    """Canonical JSON bytes (sorted keys, no incidental whitespace) so equal payloads hash equal."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def chain_link(prev_hex: str, request: bytes, response: bytes) -> str:
    """One hash-chain link: ``h_i = BLAKE2b(h_{i-1} ‖ canon(req_i) ‖ canon(resp_i))``."""
    h = hashlib.blake2b(digest_size=32)
    h.update(bytes.fromhex(prev_hex))
    h.update(request)
    h.update(response)
    return h.hexdigest()


@dataclass
class Boundary:
    """One recorded nondeterministic read."""

    seq: int
    kind: str  # "http" | "clock" | "uuid" | "rng"
    key: str  # coarse label (e.g. URL path); the full request lives in `request`
    request: Any
    response: Any
    chain_hash: str = ""
    #: 0-based count of prior boundaries sharing this ``(kind, key)`` — the *occurrence index*
    #: (algorithms-and-math §2). It is what makes loops and retries (repeated calls to the same
    #: endpoint) replay in the right order: call #0, then #1, … Derived from position, so it is
    #: recomputed on load rather than stored, and is not part of the hash-chain.
    occurrence: int = 0


def _occurrence_key(kind: str, key: str) -> str:
    """The identity a boundary's occurrence index counts against (NUL-joined to avoid collisions)."""
    return f"{kind}\x00{key}"


def occurrences(boundaries: list[Boundary]) -> list[int]:
    """The occurrence index of each boundary in order — the Nth time its ``(kind, key)`` appears."""
    counts: dict[str, int] = {}
    result: list[int] = []
    for b in boundaries:
        k = _occurrence_key(b.kind, b.key)
        result.append(counts.get(k, 0))
        counts[k] = counts.get(k, 0) + 1
    return result


@dataclass
class Cassette:
    """A complete, self-contained recording of one run."""

    boundaries: list[Boundary] = field(default_factory=list)
    fingerprint: str = GENESIS  # final hash-chain value = the run's identity
    final_output: str = ""
    provider: str = ""
    model: str = ""


class Session:
    """Mediates every boundary in ``record`` or ``replay`` mode."""

    def __init__(self, mode: Mode, cassette: Cassette | None = None) -> None:
        self.mode: Mode = mode
        self.boundaries: list[Boundary] = []
        self._recorded: list[Boundary] = cassette.boundaries if cassette else []
        self._cursor = 0
        self.chain = GENESIS
        self._in_flight = False  # guards against concurrent (asyncio.gather) boundaries
        self._live_counts: dict[str, int] = {}  # occurrence index of each (kind, key) so far
        self._rec_occurrences = occurrences(self._recorded)  # expected index at each position

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        """The one method every boundary goes through."""
        req_bytes = canon([kind, key, request])
        occ_key = _occurrence_key(kind, key)
        occurrence = self._live_counts.get(occ_key, 0)
        if self.mode == "record":
            response = produce()
            self.chain = chain_link(self.chain, req_bytes, canon(response))
            self.boundaries.append(
                Boundary(len(self.boundaries), kind, key, request, response, self.chain, occurrence)
            )
            self._live_counts[occ_key] = occurrence + 1
            return response

        seq = self._cursor
        if seq >= len(self._recorded):
            raise Divergence(
                seq,
                f"replay underflow — live {kind}/{key} has no recorded boundary "
                "(capture incomplete or the code changed since recording)",
            )
        rec = self._recorded[seq]
        if canon([rec.kind, rec.key, rec.request]) != req_bytes:
            raise Divergence(
                seq,
                f"input diverged — live {kind}/{key} does not match recorded "
                f"{rec.kind}/{rec.key} (uncaptured nondeterminism or a code change)",
            )
        if occurrence != self._rec_occurrences[seq]:
            raise Divergence(
                seq,
                f"occurrence mismatch — live {kind}/{key} is call #{occurrence}, but the "
                f"recording expected call #{self._rec_occurrences[seq]} here "
                "(a loop or retry ran a different number of times)",
            )
        self.chain = chain_link(self.chain, req_bytes, canon(rec.response))
        if self.chain != rec.chain_hash:
            raise Divergence(seq, "hash-chain mismatch — the recording was tampered or corrupted")
        self._live_counts[occ_key] = occurrence + 1
        self._cursor += 1
        return rec.response

    async def mediate_async(
        self, kind: str, key: str, request: Any, aproduce: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Async variant of :meth:`mediate` — awaits the producer, but only in record mode.

        In replay mode the producer is never awaited (network kill-switch); the recorded
        value is served exactly as in the synchronous path.

        Concurrency (v1 = serialized): a ``Session`` mutates a single hash-chain and cursor,
        so two boundaries in flight at once (e.g. ``asyncio.gather`` of HTTP calls) would
        corrupt the recording. We detect that and **fail loud** rather than silently
        mis-record. Serialize such agents, or await calls one at a time, for now.
        """
        if self.mode != "record":
            return self.mediate(kind, key, request, _unreachable)
        if self._in_flight:
            raise Divergence(
                len(self.boundaries),
                "concurrent boundary detected — v1 capture is serialized-only; "
                "avoid asyncio.gather of HTTP calls (concurrent replay is a later phase)",
            )
        self._in_flight = True
        try:
            value = await aproduce()
        finally:
            self._in_flight = False
        return self.mediate(kind, key, request, lambda: value)

    def assert_fully_consumed(self) -> None:
        """After replay, unread recorded boundaries mean the run ended early (a divergence)."""
        if self.mode == "replay" and self._cursor != len(self._recorded):
            raise Divergence(
                self._cursor,
                f"replay consumed {self._cursor} of {len(self._recorded)} boundaries — "
                "the run ended early",
            )

    # -- non-HTTP determinism shims ------------------------------------------------
    def now(self) -> float:
        return float(self.mediate("clock", "time", None, time.time))

    def new_uuid(self) -> str:
        return str(self.mediate("uuid", "uuid4", None, lambda: str(uuid.uuid4())))

    def rand(self) -> float:
        return float(self.mediate("rng", "random", None, random.random))
