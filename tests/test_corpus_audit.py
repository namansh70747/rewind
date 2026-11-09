"""Ensure corpus audit catches stored secrets without exposing matches."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from flightrecorder.boundary import Cassette, Session
from flightrecorder.corpus_audit import audit_corpus
from flightrecorder.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def test_audit_reports_leaks_and_integrity_without_revealing_secrets(tmp_path: Path) -> None:
    secret = "gsk_" + "A" * 45
    session = Session("record")
    session.mediate(
        "http",
        "fixture",
        {},
        lambda: {"chunk_bytes_b64": [base64.b64encode(secret.encode()).decode()]},
    )
    cassette = Cassette(boundaries=session.boundaries, fingerprint=session.chain)
    path = tmp_path / "runs.db"
    store = RunStore(path)
    run_id = store.save(cassette)
    store.close()
    report = audit_corpus(path)
    assert not report["passed"]
    assert report["runs_with_known_patterns"] == 1
    assert report["blobs_with_known_patterns"] == 1
    assert report["runs"][0]["run_id"] == run_id
    assert secret not in json.dumps(report)


def test_empty_store_does_not_pass(tmp_path: Path) -> None:
    report = audit_corpus(tmp_path / "empty.db")
    assert report["runs_scanned"] == 0
    assert not report["passed"]
