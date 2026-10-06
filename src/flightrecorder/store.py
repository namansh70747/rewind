"""Embedded, local-first run storage (ADR-0003 / ADR-0008).

A recording is persisted to SQLite as run metadata + an ordered boundary index, with each
request/response payload written to a **content-addressed** blob table (BLAKE2b hash,
zlib-compressed). Identical payloads — the same system prompt across many steps, repeated
tool schemas — are stored once. Zero servers; it's just a file.

**Hash split (Week 5).** The replay hash-chain is BLAKE3
(:func:`flightrecorder.boundary.chain_link`). Blob addresses in this file stay stdlib
``blake2b`` + ``zlib`` until the Week 8 log-format freeze switches storage to BLAKE3 +
zstd. A chain mismatch is a divergence; a blob hash is only a storage address.
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
        digest = hashlib.blake2b(raw, digest_size=32).hexdigest()
        self.conn.execute(
            "INSERT OR IGNORE INTO blob (hash, data) VALUES (?, ?)", (digest, zlib.compress(raw))
        )
        return digest

    def _get_blob(self, digest: str) -> Any:
        row = self.conn.execute("SELECT data FROM blob WHERE hash = ?", (digest,)).fetchone()
        if row is None:
            raise KeyError(f"blob {digest} not found")
        return json.loads(zlib.decompress(row[0]))

    def save(self, cassette: Cassette) -> str:
        """Persist a recording; returns its run id."""
        run_id = uuid.uuid4().hex[:12]
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
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
        self.conn.commit()
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
        return Cassette(
            boundaries=boundaries,
            fingerprint=meta[0],
            final_output=meta[1],
            provider=meta[2],
            model=meta[3],
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

    def close(self) -> None:
        self.conn.close()
