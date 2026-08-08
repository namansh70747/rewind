"""The record/replay engine for Spike A.

One idea does all the work: an agent run is a sequence of **boundary reads** — every
value the agent gets from the nondeterministic outside world (an LLM HTTP response, the
clock, a UUID, an RNG draw). We record those values once; on replay we serve them back
and never touch the network. A per-boundary **hash-chain** lets us prove the replay is
faithful and localize the exact point of any divergence.

See ADR-0006 (replay is playback, not re-execution) and ADR-0007 (capture at the httpx
transport layer).
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

Mode = Literal["record", "replay"]

# 32 zero bytes, hex-encoded: the genesis link of every run's hash-chain.
GENESIS = "00" * 32


class Divergence(Exception):
    """Raised the instant replay stops matching the recording.

    A debugger that lies silently is worse than none, so every mismatch is loud and
    names the boundary where it happened.
    """

    def __init__(self, seq: int, message: str) -> None:
        self.seq = seq
        super().__init__(f"boundary #{seq}: {message}")


def canon(obj: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, no incidental whitespace.

    Semantically-equal payloads must hash equal, so serialization must be stable.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _link(prev_hex: str, request: bytes, response: bytes) -> str:
    """One link of the hash-chain: h_i = H(h_{i-1} || canon(req_i) || canon(resp_i))."""
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
    key: str  # a coarse label (e.g. the URL path); full request lives in `request`
    request: Any
    response: Any
    chain_hash: str = ""


@dataclass
class Cassette:
    """A complete recording of one run."""

    boundaries: list[Boundary] = field(default_factory=list)
    fingerprint: str = GENESIS  # the final hash-chain value = the run's identity
    final_output: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> Cassette:
        raw = json.loads(text)
        boundaries = [Boundary(**b) for b in raw["boundaries"]]
        return Cassette(
            boundaries=boundaries,
            fingerprint=raw["fingerprint"],
            final_output=raw["final_output"],
        )


class Session:
    """Mediates every boundary in one of two modes.

    * ``record`` — call the real world, log the value, extend the hash-chain.
    * ``replay`` — serve the recorded value; NEVER call the real world; verify the
      hash-chain link by link and raise :class:`Divergence` at the first mismatch.
    """

    def __init__(self, mode: Mode, cassette: Cassette | None = None) -> None:
        self.mode: Mode = mode
        self.boundaries: list[Boundary] = []
        self._recorded: list[Boundary] = cassette.boundaries if cassette else []
        self._cursor = 0
        self.chain = GENESIS

    # -- the one method every boundary goes through --------------------------------
    def _boundary(self, kind: str, key: str, request: Any, produce: Callable[[], Any]) -> Any:
        req_bytes = canon([kind, key, request])
        if self.mode == "record":
            response = produce()
            self.chain = _link(self.chain, req_bytes, canon(response))
            self.boundaries.append(
                Boundary(len(self.boundaries), kind, key, request, response, self.chain)
            )
            return response

        # replay
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
        self.chain = _link(self.chain, req_bytes, canon(rec.response))
        if self.chain != rec.chain_hash:
            raise Divergence(seq, "hash-chain mismatch — the recording was tampered or corrupted")
        self._cursor += 1
        return rec.response

    def assert_fully_consumed(self) -> None:
        """After replay, unread recorded boundaries mean the run diverged (took fewer steps)."""
        if self.mode == "replay" and self._cursor != len(self._recorded):
            raise Divergence(
                self._cursor,
                f"replay consumed {self._cursor} of {len(self._recorded)} boundaries — "
                "the run ended early (divergence)",
            )

    # -- non-HTTP determinism shims ------------------------------------------------
    def now(self) -> float:
        return float(self._boundary("clock", "time", None, time.time))

    def new_uuid(self) -> str:
        return str(self._boundary("uuid", "uuid4", None, lambda: str(uuid.uuid4())))

    def rand(self) -> float:
        return float(self._boundary("rng", "random", None, random.random))


class RecordingTransport(httpx.BaseTransport):
    """An httpx transport that routes every HTTP call through the :class:`Session`.

    In replay mode ``inner`` is never touched — that is the network kill-switch: no
    outbound request can escape unless it was served from the recording.
    """

    def __init__(self, session: Session, inner: httpx.BaseTransport | None = None) -> None:
        self._session = session
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        req_repr: dict[str, Any] = {
            "method": request.method,
            "url": str(request.url),
            "body": json.loads(body) if body else None,
        }

        def produce() -> dict[str, Any]:
            if self._inner is None:  # pragma: no cover - defensive
                raise RuntimeError("record mode requires an inner transport")
            resp = self._inner.handle_request(request)
            resp.read()
            return {"status": resp.status_code, "body": json.loads(resp.content)}

        rec = self._session._boundary("http", request.url.path, req_repr, produce)
        return httpx.Response(status_code=rec["status"], json=rec["body"], request=request)
