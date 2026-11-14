"""Embedded, local-first run storage (ADR-0003 / ADR-0008).

A recording is persisted to SQLite as run metadata + an ordered boundary index, with each
request/response payload written to a **content-addressed** blob table (BLAKE3 hash,
zstd-compressed). Identical payloads — the same system prompt across many steps, repeated
tool schemas — are stored once. Zero servers; it's just a file.

New blobs have a b3: prefix and zstd compression. Legacy unprefixed BLAKE2b/zlib
blobs remain readable; migration does not silently reinterpret their bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import zstandard
from blake3 import blake3

from .boundary import Boundary, Cassette, canon

DEFAULT_DB = ".rewind/runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    id            TEXT PRIMARY KEY,
    fingerprint   TEXT NOT NULL,
    final_output  TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    n_boundaries  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS boundary (
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    req_hash    TEXT NOT NULL,
    resp_hash   TEXT NOT NULL,
    chain_hash  TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS run_metadata (
    run_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot (
    run_id TEXT NOT NULL, seq INTEGER NOT NULL, observed_hash TEXT NOT NULL,
    state_hash TEXT NOT NULL, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS blob (
    hash TEXT PRIMARY KEY,
    data BLOB NOT NULL
);
"""


@dataclass(frozen=True)
class RunSummary:
    id: str
    provider: str
    model: str
    n_boundaries: int
    created_at: str
    fingerprint: str


class RunStore:
    """SQLite-backed store of recordings with a content-addressed blob table."""

    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    def _put_blob(self, obj: Any) -> str:
        raw = canon(obj)
        digest = "b3:" + blake3(raw).hexdigest()
        self.conn.execute(
            "INSERT OR IGNORE INTO blob (hash, data) VALUES (?, ?)",
            (digest, zstandard.ZstdCompressor(level=3).compress(raw)),
        )
        return digest

    def _get_blob(self, digest: str) -> Any:
        row = self.conn.execute("SELECT data FROM blob WHERE hash = ?", (digest,)).fetchone()
        if row is None:
            raise KeyError(f"blob {digest} not found")
        raw = (
            zstandard.ZstdDecompressor().decompress(row[0], max_output_size=32 * 1024 * 1024)
            if digest.startswith("b3:")
            else zlib.decompress(row[0])
        )
        actual = (
            "b3:" + blake3(raw).hexdigest()
            if digest.startswith("b3:")
            else hashlib.blake2b(raw, digest_size=32).hexdigest()
        )
        if actual != digest:
            raise ValueError(f"corrupted content-addressed blob {digest}")
        return json.loads(raw)

    def save(self, cassette: Cassette) -> str:
        """Persist a recording; returns its run id."""
        run_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        from .integrity import validate

        validate(cassette)
        with self.conn:
            return self._save(cassette, run_id, created_at)

    def _save(self, cassette: Cassette, run_id: str, created_at: str) -> str:
        for b in cassette.boundaries:
            req_hash = self._put_blob(b.request)
            resp_hash = self._put_blob(b.response)
            self.conn.execute(
                "INSERT INTO boundary VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, b.seq, b.kind, b.key, req_hash, resp_hash, b.chain_hash),
            )
        self.conn.execute(
            "INSERT INTO run VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                cassette.fingerprint,
                cassette.final_output,
                cassette.provider,
                cassette.model,
                created_at,
                len(cassette.boundaries),
            ),
        )
        self.conn.execute(
            "INSERT INTO run_metadata VALUES (?, ?)",
            (
                run_id,
                canon({**cassette.metadata, "_chain_algorithm": cassette.chain_algorithm}).decode(),
            ),
        )
        return run_id

    def load(self, run_id: str) -> Cassette:
        meta = self.conn.execute(
            "SELECT fingerprint, final_output, provider, model FROM run WHERE id = ?", (run_id,)
        ).fetchone()
        if meta is None:
            raise KeyError(f"run {run_id} not found")
        rows = self.conn.execute(
            "SELECT seq, kind, key, req_hash, resp_hash, chain_hash "
            "FROM boundary WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        boundaries = [
            Boundary(seq, kind, key, self._get_blob(rq), self._get_blob(rs), ch)
            for (seq, kind, key, rq, rs, ch) in rows
        ]
        metadata = self.conn.execute(
            "SELECT data FROM run_metadata WHERE run_id = ?", (run_id,)
        ).fetchone()
        details = json.loads(metadata[0]) if metadata else {}
        algorithm = details.pop("_chain_algorithm", "blake2b")
        return Cassette(
            boundaries=boundaries,
            fingerprint=meta[0],
            final_output=meta[1],
            provider=meta[2],
            model=meta[3],
            metadata=details,
            chain_algorithm=algorithm,
        )

    def list_runs(self) -> list[RunSummary]:
        rows = self.conn.execute(
            "SELECT id, provider, model, n_boundaries, created_at, fingerprint "
            "FROM run ORDER BY created_at DESC"
        ).fetchall()
        return [RunSummary(*row) for row in rows]

    def blob_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM blob").fetchone()
        return int(row[0])

    def index_snapshots(self, run_id: str, interval: int | None = None) -> int:
        """Persist COW checkpoint manifests; response payloads reuse existing CAS blobs."""
        from .integrity import validate

        cassette = self.load(run_id)
        validate(cassette)
        k = max(1, math.isqrt(len(cassette.boundaries))) if interval is None else interval
        if type(k) is not int or k < 1:
            raise ValueError("snapshot interval must be a positive integer")
        references: dict[str, str] = {}
        pending: dict[str, str] = {}
        base: str | None = None
        state_digest = self._put_blob(None)
        count = 0
        with self.conn:
            self.conn.execute("DELETE FROM snapshot WHERE run_id = ?", (run_id,))
            for boundary in cassette.boundaries:
                identity = f"{boundary.kind}:{boundary.key}"
                digest = self._put_blob(boundary.response)
                if references.get(identity) != digest:
                    references[identity] = pending[identity] = digest
                if boundary.kind == "state":
                    state_digest = digest
                if boundary.seq % k:
                    continue
                # Sparse full anchors bound ancestry; intervening writes contain
                # only changed references, never the whole observed map.
                if count % k == 0:
                    base = None
                    updates = references.copy()
                else:
                    updates = pending.copy()
                manifest = {
                    "schema": "rewind.snapshot-delta",
                    "version": 1,
                    "base": base,
                    "updates": updates,
                    "run_fingerprint": cassette.fingerprint,
                    "seq": boundary.seq,
                    "chain_hash": boundary.chain_hash,
                }
                digest = self._put_blob(manifest)
                self.conn.execute(
                    "INSERT INTO snapshot VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        boundary.seq,
                        digest,
                        self._put_blob(
                            {
                                "schema": "rewind.snapshot-state-ref",
                                "version": 1,
                                "response_hash": state_digest,
                                "run_fingerprint": cassette.fingerprint,
                                "seq": boundary.seq,
                            }
                        ),
                    ),
                )
                base = digest
                pending.clear()
                count += 1
        return count

    def _snapshot_refs(self, digest: str) -> tuple[dict[str, str], set[str]]:
        """Resolve bounded delta ancestry; also read pre-envelope legacy snapshots."""
        manifests = []
        visited: set[str] = set()
        while digest:
            if digest in visited:
                raise ValueError("cyclic snapshot manifest")
            visited.add(digest)
            manifest = self._get_blob(digest)
            if manifest.get("schema") != "rewind.snapshot-delta":
                manifests.append(manifest)
                break
            if manifest.get("version") != 1 or set(manifest) != {
                "schema",
                "version",
                "base",
                "updates",
                "run_fingerprint",
                "seq",
                "chain_hash",
            }:
                raise ValueError("unsupported snapshot manifest")
            manifests.append(manifest["updates"])
            digest = manifest["base"]
        refs: dict[str, str] = {}
        for updates in reversed(manifests):
            refs.update(updates)
        return refs, visited

    def snapshot_at(self, run_id: str, at: int) -> dict[str, Any]:
        """Load nearest persisted checkpoint and at most one interval of boundaries."""
        maximum = self.conn.execute(
            "SELECT n_boundaries, final_output, fingerprint FROM run WHERE id = ?", (run_id,)
        ).fetchone()
        if type(at) is not int or maximum is None or not 0 <= at < maximum[0]:
            raise ValueError("boundary index is outside recording")
        row = self.conn.execute(
            "SELECT seq, observed_hash, state_hash FROM snapshot "
            "WHERE run_id = ? AND seq <= ? ORDER BY seq DESC LIMIT 1",
            (run_id, at),
        ).fetchone()
        if row is None:
            self.index_snapshots(run_id)
            return self.snapshot_at(run_id, at)
        seq, observed_hash, state_hash = row
        manifest = self._get_blob(observed_hash)
        if manifest.get("schema") == "rewind.snapshot-delta":
            expected_chain = self.conn.execute(
                "SELECT chain_hash FROM boundary WHERE run_id=? AND seq=?", (run_id, seq)
            ).fetchone()[0]
            if (
                manifest.get("run_fingerprint") != maximum[2]
                or manifest.get("seq") != seq
                or manifest.get("chain_hash") != expected_chain
            ):
                raise ValueError(
                    "snapshot does not belong to this recording boundary; rebuild its index"
                )
        refs, _ = self._snapshot_refs(observed_hash)
        observed = {key: self._get_blob(value) for key, value in refs.items()}
        from .state import decode_state

        state = self._get_blob(state_hash)
        if isinstance(state, dict) and state.get("schema") == "rewind.snapshot-state-ref":
            if state.get("version") != 1 or set(state) != {
                "schema",
                "version",
                "response_hash",
                "run_fingerprint",
                "seq",
            }:
                raise ValueError("unsupported snapshot state reference")
            if state.get("run_fingerprint") != maximum[2] or state.get("seq") != seq:
                raise ValueError("snapshot state does not belong to this recording boundary")
            state = self._get_blob(state["response_hash"])
        elif isinstance(state, dict) and state.get("schema") == "rewind.logical-state":
            state = decode_state(state)
        for kind, key, digest in self.conn.execute(
            "SELECT kind, key, resp_hash FROM boundary WHERE run_id = ? AND seq > ? AND seq <= ? ORDER BY seq",
            (run_id, seq, at),
        ):
            value = self._get_blob(digest)
            observed[f"{kind}:{key}"] = value
            if kind == "state":
                state = value
        boundary = self.conn.execute(
            "SELECT kind, key, req_hash, resp_hash, chain_hash FROM boundary WHERE run_id=? AND seq=?",
            (run_id, at),
        ).fetchone()
        return {
            "schema_version": 1,
            "boundary": {
                "seq": at,
                "kind": boundary[0],
                "key": boundary[1],
                "request": self._get_blob(boundary[2]),
                "response": self._get_blob(boundary[3]),
                "chain_hash": boundary[4],
            },
            "final_output": maximum[1] if at == maximum[0] - 1 else None,
            "at": at,
            "checkpoint": seq,
            "replayed_events": at - seq,
            "observed": observed,
            "agent_snapshot": state,
        }

    def storage_stats(self) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT count(*), coalesce(sum(length(data)),0) FROM blob"
        ).fetchone()
        refs = self.conn.execute("SELECT count(*) * 2 FROM boundary").fetchone()[0]
        return {
            "unique_blobs": int(row[0]),
            "compressed_bytes": int(row[1]),
            "references": int(refs),
        }

    def garbage_collect(self) -> int:
        """Delete only unreachable blobs. Live recording references remain untouched."""
        reachable = {
            row[0]
            for row in self.conn.execute(
                "SELECT req_hash FROM boundary UNION SELECT resp_hash FROM boundary "
                "UNION SELECT observed_hash FROM snapshot UNION SELECT state_hash FROM snapshot"
            )
        }
        for (digest,) in self.conn.execute("SELECT observed_hash FROM snapshot"):
            refs, ancestors = self._snapshot_refs(digest)
            reachable.update(ancestors)
            reachable.update(refs.values())
        for (digest,) in self.conn.execute("SELECT state_hash FROM snapshot"):
            state = self._get_blob(digest)
            if isinstance(state, dict) and state.get("schema") == "rewind.snapshot-state-ref":
                reachable.add(state["response_hash"])
        garbage = [
            (row[0],)
            for row in self.conn.execute("SELECT hash FROM blob")
            if row[0] not in reachable
        ]
        with self.conn:
            self.conn.executemany("DELETE FROM blob WHERE hash = ?", garbage)
        return len(garbage)

    def close(self) -> None:
        self.conn.close()
