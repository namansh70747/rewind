"""Month 6: LoRA explainer stub, concurrent replay, GC, and benchmark gate."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from flightrecorder.boundary import Cassette, Session
from flightrecorder.cli import app
from flightrecorder.month5 import record_failure
from flightrecorder.month6 import (
    ConcurrentReplayResult,
    RetentionReport,
    benchmark_replay,
    concurrent_replay,
    explain,
    retention_gc,
)
from flightrecorder.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# explain() — deterministic narration from recorded evidence
# ---------------------------------------------------------------------------


def test_explain_uses_classifier_label_when_supplied() -> None:
    cassette = record_failure("tool-error")
    report = explain(
        cassette,
        classifier_report={"label": "tool-error", "probabilities": {"tool-error": 0.92}},
        run_id="test-run-01",
    )
    assert report["label"] == "tool-error"
    assert report["label_source"] == "classifier"
    assert report["probability"] == pytest.approx(0.92)
    assert "tool" in report["cause"].lower()
    assert any("fr show" in step for step in report["next_steps"])


def test_explain_falls_back_to_weak_label() -> None:
    cassette = record_failure("transport-timeout")
    report = explain(cassette, run_id="test-run-02")
    # No classifier supplied; weak-label or bisect-metadata should kick in.
    assert report["label_source"] in (
        "weak-label",
        "bisect-metadata",
        "metadata-family",
        "none",
    )
    assert isinstance(report["cause"], str)
    assert len(report["cause"]) > 10


def test_explain_all_three_families_produce_distinct_causes() -> None:
    causes = set()
    for family in ("tool-error", "transport-timeout", "context-budget"):
        cassette = record_failure(family)
        report = explain(
            cassette,
            classifier_report={"label": family, "probabilities": {family: 0.85}},
        )
        causes.add(report["cause"])
    # Three different families → three distinct narration sentences.
    assert len(causes) == 3


def test_explain_qualification_mentions_lora() -> None:
    cassette = record_failure("tool-error")
    report = explain(cassette)
    assert "lora" in report["qualification"].lower() or "LoRA" in report["qualification"]
    assert report["lora_status"].startswith("deferred")


def test_explain_schema_field_present() -> None:
    cassette = record_failure("context-budget")
    report = explain(cassette)
    assert report["schema"] == "rewind.explain.v1"
    assert isinstance(report["feature_summary"], dict)


def test_explain_unknown_label_produces_default_sentence() -> None:
    cassette = record_failure("tool-error")
    report = explain(
        cassette,
        classifier_report={"label": "mystery-new-failure", "probabilities": {}},
    )
    assert "mystery-new-failure" in report["cause"]


# ---------------------------------------------------------------------------
# concurrent_replay() — parallel replay with thread pool
# ---------------------------------------------------------------------------


def _make_simple_run() -> Cassette:
    """A tiny cassette: one tool boundary, deterministic."""
    session = Session("record")
    session.mediate("tool", "ping", {}, lambda: {"ok": True})
    return Cassette(session.boundaries, session.chain, "pong", "", "", {})


def _replay_fn(session: Session, _transport: object) -> str:
    """Replay fn that serves the recorded boundary value."""
    session.mediate("tool", "ping", {}, lambda: {"ok": True})
    return "pong"


def test_concurrent_replay_all_pass() -> None:
    cassette = _make_simple_run()
    result = concurrent_replay(cassette, _replay_fn, n=4, max_workers=2)
    assert isinstance(result, ConcurrentReplayResult)
    assert result.passed == 4
    assert result.failed == 0
    assert result.elapsed_s >= 0
    assert result.throughput_replays_per_s > 0


def test_concurrent_replay_n_1_works() -> None:
    cassette = _make_simple_run()
    result = concurrent_replay(cassette, _replay_fn, n=1)
    assert result.n == 1
    assert result.passed == 1


def test_concurrent_replay_invalid_n_raises() -> None:
    cassette = _make_simple_run()
    with pytest.raises(ValueError, match="at least 1"):
        concurrent_replay(cassette, _replay_fn, n=0)


def test_concurrent_replay_str_reports_summary() -> None:
    cassette = _make_simple_run()
    result = concurrent_replay(cassette, _replay_fn, n=2, max_workers=1)
    text = str(result)
    assert "concurrent replay" in text
    assert "2/2" in text


# ---------------------------------------------------------------------------
# retention_gc() — keep_last and max_age_days
# ---------------------------------------------------------------------------


def test_retention_gc_requires_at_least_one_criterion(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    with pytest.raises(ValueError, match="keep_last or max_age_days"):
        retention_gc(db)


def test_retention_gc_negative_keep_last_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    with pytest.raises(ValueError, match="non-negative"):
        retention_gc(db, keep_last=-1)


def test_retention_gc_non_positive_max_age_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    with pytest.raises(ValueError, match="positive"):
        retention_gc(db, max_age_days=0)


def test_retention_gc_keep_last_deletes_older_runs(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        for family in ("tool-error", "transport-timeout", "context-budget"):
            store.save(record_failure(family))
        assert len(list(store.list_runs())) == 3
    finally:
        store.close()

    report = retention_gc(db, keep_last=1)
    assert isinstance(report, RetentionReport)
    assert report.runs_deleted == 2
    assert report.runs_retained == 1

    store2 = RunStore(db)
    try:
        assert len(list(store2.list_runs())) == 1
    finally:
        store2.close()


def test_retention_gc_keep_last_0_deletes_all(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        store.save(record_failure("tool-error"))
        store.save(record_failure("transport-timeout"))
    finally:
        store.close()

    report = retention_gc(db, keep_last=0)
    assert report.runs_deleted == 2
    assert report.runs_retained == 0


def test_retention_gc_dry_run_does_not_delete(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        store.save(record_failure("tool-error"))
        store.save(record_failure("context-budget"))
    finally:
        store.close()

    report = retention_gc(db, keep_last=1, dry_run=True)
    assert report.runs_deleted == 1
    # Dry run: nothing actually removed.
    store2 = RunStore(db)
    try:
        assert len(list(store2.list_runs())) == 2
    finally:
        store2.close()


def test_retention_gc_max_age_days_future_keeps_all(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        store.save(record_failure("tool-error"))
    finally:
        store.close()

    # 999 days in the future — nothing should be deleted.
    report = retention_gc(db, max_age_days=999)
    assert report.runs_deleted == 0
    assert report.runs_retained == 1


def test_retention_gc_str_representation() -> None:
    r = RetentionReport(runs_deleted=3, runs_retained=7, blobs_collected=12)
    text = str(r)
    assert "deleted 3" in text
    assert "retained 7" in text
    assert "12" in text


# ---------------------------------------------------------------------------
# benchmark_replay() — structured evidence record
# ---------------------------------------------------------------------------


def test_benchmark_replay_schema_and_fields() -> None:
    cassette = _make_simple_run()
    report = benchmark_replay(cassette, _replay_fn, n=4, max_workers=2)
    assert report["schema"] == "rewind.benchmark.v1"
    assert report["n_replays"] == 4
    assert report["passed"] + report["failed"] == 4
    assert report["elapsed_s"] >= 0
    assert report["throughput_replays_per_s"] >= 0
    assert "qualification" in report


def test_benchmark_replay_invalid_params_raise() -> None:
    cassette = _make_simple_run()
    with pytest.raises(ValueError):
        benchmark_replay(cassette, _replay_fn, n=0)
    with pytest.raises(ValueError):
        benchmark_replay(cassette, _replay_fn, max_workers=0)


# ---------------------------------------------------------------------------
# CLI smoke — fr explain and fr gc
# ---------------------------------------------------------------------------


runner = CliRunner()


def test_fr_explain_smoke(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        run_id = store.save(record_failure("tool-error"))
    finally:
        store.close()

    result = runner.invoke(app, ["explain", run_id, "--db", db])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema"] == "rewind.explain.v1"
    assert data["run_id"] == run_id


def test_fr_gc_smoke(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        store.save(record_failure("tool-error"))
        store.save(record_failure("transport-timeout"))
        store.save(record_failure("context-budget"))
    finally:
        store.close()

    result = runner.invoke(app, ["gc", "--db", db, "--keep-last", "2"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_fr_gc_dry_run_prints_note(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    store = RunStore(db)
    try:
        store.save(record_failure("tool-error"))
    finally:
        store.close()

    result = runner.invoke(app, ["gc", "--db", db, "--keep-last", "0", "--dry-run"])
    assert result.exit_code == 0
    assert "dry run" in result.output.lower()


def test_fr_gc_missing_criterion_exits_nonzero(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    result = runner.invoke(app, ["gc", "--db", db])
    assert result.exit_code != 0


def test_concurrent_verifier_rejects_wrong_final_output() -> None:
    def wrong(session: Session, transport: object) -> str:
        _replay_fn(session, transport)
        return "wrong output"

    result = concurrent_replay(_make_simple_run(), wrong, n=8, max_workers=4)
    assert result.passed == 0
    assert result.failed == 8
    assert len(result.errors) == 8


def test_concurrent_verifier_rejects_invalid_workers() -> None:
    with pytest.raises(ValueError, match="max_workers"):
        concurrent_replay(_make_simple_run(), _replay_fn, n=1, max_workers=0)


def test_overlapping_guards_do_not_restore_each_others_patches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from flightrecorder.offline import NetworkBlocked, offline_guard

    def original(*args: object, **kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(socket, "getaddrinfo", original)
    entered, first_exited = Event(), Event()

    def second() -> None:
        with offline_guard() as audit:
            entered.set()
            assert first_exited.wait(2)
            with pytest.raises(NetworkBlocked):
                socket.getaddrinfo("fixture.invalid", 80)
            assert audit.blocked_operations == ["getaddrinfo"]

    with ThreadPoolExecutor(max_workers=1) as pool:
        with offline_guard():
            future = pool.submit(second)
            assert entered.wait(2)
        first_exited.set()
        future.result(timeout=3)
    assert socket.getaddrinfo is original


def test_authorized_network_does_not_unblock_other_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    from concurrent.futures import ThreadPoolExecutor

    import flightrecorder.offline as offline

    def fake_dns(*args: object, **kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(offline, "_DNS_ORIGINAL", fake_dns)
    with offline.offline_guard() as audit, offline.authorized_network():
        assert socket.getaddrinfo("fixture.invalid", 80) == []
        with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(offline.NetworkBlocked):
            pool.submit(socket.getaddrinfo, "fixture.invalid", 80).result(timeout=2)
    assert audit.blocked_operations == ["getaddrinfo"]


def test_explanation_does_not_turn_weak_labels_into_proven_causes() -> None:
    report = explain(_make_simple_run(), classifier_report={"label": "sampling-flake"})
    assert "not a proven cause" in report["cause"]
    report = explain(_make_simple_run(), classifier_report={"label": "arg-hallucination"})
    assert "not proof of hallucination" in report["cause"]


def test_explicit_guard_overrides_an_outer_live_authorization() -> None:
    import socket

    from flightrecorder.offline import NetworkBlocked, authorized_network, offline_guard

    with authorized_network(), offline_guard() as audit, pytest.raises(NetworkBlocked):
        socket.getaddrinfo("fixture.invalid", 80)
    assert audit.blocked_operations == ["getaddrinfo"]
