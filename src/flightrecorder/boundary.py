"""The spine: a ``Session`` that mediates every nondeterministic boundary.

An agent run is a sequence of **boundary reads** — every value the agent gets from the
outside world (an LLM HTTP response, the clock, a UUID, an RNG draw). ``RECORD`` calls
the real world and logs the value; ``REPLAY`` serves the recorded value, never calls out,
and verifies a BLAKE3 **hash-chain** link by link, raising :class:`Divergence` — loud and
localized — at the first mismatch.

See ADR-0006 (replay is playback, not re-execution) and ADR-0008 (our own recording
schema). HTTP capture lives in :mod:`flightrecorder.interceptors.transport` (ADR-0007);
clock/uuid/rng are shimmed here.

New recordings use BLAKE3; legacy BLAKE2b chains remain readable through the
explicit chain_algorithm field. Format review and release acceptance remain separate
from implementation compatibility.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from blake3 import blake3

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
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def chain_link(prev_hex: str, request: bytes, response: bytes, algorithm: str = "blake3") -> str:
    """One hash-chain link: ``h_i = H(h_{i-1} ‖ canon(req_i) ‖ canon(resp_i)); H defaults to BLAKE3``."""
    if algorithm not in {"blake3", "blake2b"}:
        raise ValueError(f"unsupported chain algorithm: {algorithm}")
    h = blake3() if algorithm == "blake3" else hashlib.blake2b(digest_size=32)
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
    metadata: dict[str, Any] = field(default_factory=dict)
    chain_algorithm: str = "blake3"


class Session:
    """Mediates every boundary in ``record`` or ``replay`` mode."""

    def __init__(self, mode: Mode, cassette: Cassette | None = None) -> None:
        if mode not in ("record", "replay"):
            raise ValueError(f"unknown session mode: {mode}")
        self.algorithm = cassette.chain_algorithm if cassette else "blake3"
        self.mode: Mode = mode
        self.boundaries: list[Boundary] = []
        self._recorded: list[Boundary] = cassette.boundaries if cassette else []
        self._cursor = 0
        self.chain = GENESIS
        self._in_flight = False  # guards against concurrent (asyncio.gather) boundaries

    def mediate(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        """The one method every boundary goes through."""
        req_bytes = canon([kind, key, request])
        if self.mode == "record":
            response = produce()
            self.chain = chain_link(self.chain, req_bytes, canon(response), self.algorithm)
            self.boundaries.append(
                Boundary(
                    len(self.boundaries),
                    kind,
                    key,
                    copy.deepcopy(request),
                    copy.deepcopy(response),
                    self.chain,
                )
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
        self.chain = chain_link(self.chain, req_bytes, canon(rec.response), self.algorithm)
        if self.chain != rec.chain_hash:
            raise Divergence(seq, "hash-chain mismatch — the recording was tampered or corrupted")
        self._cursor += 1
        return copy.deepcopy(rec.response)

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
