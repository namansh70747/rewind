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
        from .snapshots import SnapshotIndex

        index = SnapshotIndex(self.load(run_id), interval)
        with self.conn:
            self.conn.execute("DELETE FROM snapshot WHERE run_id = ?", (run_id,))
            for seq, (observed, state) in index.checkpoints.items():
                references = {key: self._put_blob(value) for key, value in observed.items()}
                self.conn.execute(
                    "INSERT INTO snapshot VALUES (?, ?, ?, ?)",
                    (run_id, seq, self._put_blob(references), self._put_blob(state)),
                )
        return len(index.checkpoints)

    def snapshot_at(self, run_id: str, at: int) -> dict[str, Any]:
        """Load nearest persisted checkpoint and at most one interval of boundaries."""
        maximum = self.conn.execute(
            "SELECT n_boundaries FROM run WHERE id = ?", (run_id,)
        ).fetchone()
        if maximum is None or not 0 <= at < maximum[0]:
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
        refs = self._get_blob(observed_hash)
        observed = {key: self._get_blob(value) for key, value in refs.items()}
        state = self._get_blob(state_hash)
        for kind, key, digest in self.conn.execute(
            "SELECT kind, key, resp_hash FROM boundary WHERE run_id = ? AND seq > ? AND seq <= ? ORDER BY seq",
            (run_id, seq, at),
        ):
            value = self._get_blob(digest)
            observed[f"{kind}:{key}"] = value
            if kind == "state":
                state = value
        return {
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
            reachable.update(self._get_blob(digest).values())
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
