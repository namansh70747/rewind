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
    from collections.abc import Callable

Mode = Literal["record", "replay"]

#: 32 zero bytes, hex-encoded — the genesis link of every run's hash-chain.
GENESIS = "00" * 32


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

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        """The one method every boundary goes through."""
        req_bytes = canon([kind, key, request])
        if self.mode == "record":
            response = produce()
            self.chain = chain_link(self.chain, req_bytes, canon(response))
            self.boundaries.append(
                Boundary(len(self.boundaries), kind, key, request, response, self.chain)
            )
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
        self.chain = chain_link(self.chain, req_bytes, canon(rec.response))
        if self.chain != rec.chain_hash:
            raise Divergence(seq, "hash-chain mismatch — the recording was tampered or corrupted")
        self._cursor += 1
        return rec.response

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
