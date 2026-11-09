"""Inspect local stored evidence for integrity and known redaction patterns.

The report contains counts and run IDs, never recording contents or matched values.
It is a heuristic scan, not a guarantee that all secrets or every disk copy are clean.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .integrity import validate
from .redaction import redact, redact_text
from .store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def _scan(value: Any) -> tuple[bool, bool]:
    """Scan structured values and assembled stored stream bytes without exposing them."""
    invalid_stream = False
    if isinstance(value, dict):
        matched = False
        for key, item in value.items():
            if key == "chunk_bytes_b64":
                try:
                    if not isinstance(item, list) or not all(
                        isinstance(chunk, str) for chunk in item
                    ):
                        raise ValueError("invalid chunk encoding")
                    data = b"".join(base64.b64decode(chunk, validate=True) for chunk in item)
                    text = data.decode("utf-8")
                    matched = matched or redact_text(text) != text
                except (ValueError, UnicodeDecodeError, binascii.Error):
                    invalid_stream = True
            elif isinstance(item, (dict, list)):
                matched = matched or redact({key: None}) != {key: None}
                if (
                    key == "chunks"
                    and isinstance(item, list)
                    and all(isinstance(chunk, str) for chunk in item)
                ):
                    text = "".join(item)
                    matched = matched or redact_text(text) != text
                child_match, child_invalid = _scan(item)
                matched = matched or child_match
                invalid_stream = invalid_stream or child_invalid
            else:
                matched = matched or redact({key: item}) != {key: item}
        return matched, invalid_stream
    if isinstance(value, list):
        matches = [_scan(item) for item in value]
        return any(row[0] for row in matches), any(row[1] for row in matches)
    return redact(value) != value, False


def audit_corpus(db: str | Path) -> dict[str, Any]:
    """Audit all logical recordings and blob objects in a local store, read only."""
    store = RunStore(db)
    try:
        runs = store.list_runs()
        rows: list[dict[str, Any]] = []
        for item in runs:
            try:
                cassette = store.load(item.id)
                validate(cassette)
                matched, invalid = _scan(asdict(cassette))
                rows.append(
                    {
                        "run_id": item.id,
                        "integrity": "pass",
                        "known_pattern_match": matched,
                        "invalid_stream_encoding": invalid,
                    }
                )
            except Exception:
                rows.append(
                    {
                        "run_id": item.id,
                        "integrity": "failed",
                        "known_pattern_match": None,
                        "invalid_stream_encoding": None,
                    }
                )
        blobs = store.conn.execute("SELECT hash FROM blob").fetchall()
        flagged_blobs = invalid_blobs = unreadable_blobs = 0
        for (digest,) in blobs:
            try:
                matched, invalid = _scan(store._get_blob(digest))
                flagged_blobs += int(matched)
                invalid_blobs += int(invalid)
            except Exception:
                unreadable_blobs += 1
        integrity_failures = sum(row["integrity"] == "failed" for row in rows)
        flagged_runs = sum(row["known_pattern_match"] is True for row in rows)
        invalid_runs = sum(row["invalid_stream_encoding"] is True for row in rows)
        return {
            "passed": bool(runs)
            and not any(
                (
                    integrity_failures,
                    flagged_runs,
                    invalid_runs,
                    flagged_blobs,
                    invalid_blobs,
                    unreadable_blobs,
                )
            ),
            "runs_scanned": len(runs),
            "blobs_scanned": len(blobs),
            "integrity_failures": integrity_failures,
            "runs_with_known_patterns": flagged_runs,
            "blobs_with_known_patterns": flagged_blobs,
            "runs_with_invalid_stream_bytes": invalid_runs,
            "blobs_with_invalid_stream_bytes": invalid_blobs,
            "unreadable_blobs": unreadable_blobs,
            "runs": rows,
            "scope": "Known-pattern scan of logical recordings and stored blob objects, including decoded stream chunks. Does not scan SQLite free pages, backups, exports or all possible secrets; not a security certification.",
        }
    finally:
        store.close()
