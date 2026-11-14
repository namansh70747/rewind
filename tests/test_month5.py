"""Month 5: neighbors, clusters, eval gate, query DSL, and fresh-failure match."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from typer.testing import CliRunner

from flightrecorder.boundary import Cassette, Session
from flightrecorder.cli import app
from flightrecorder.month5 import (
    cluster_agreement,
    failure_corpus,
    match_failure,
    nearest,
    policy_gate,
    record_failure,
)
from flightrecorder.query import query
from flightrecorder.run_features import run_features
from flightrecorder.store import RunStore


def test_named_queries_find_tool_errors_retries_and_context() -> None:
    cassette = record_failure("transport-timeout")
    budget = record_failure("context-budget")
    broken = record_failure("tool-error")
    assert [row["seq"] for row in query(cassette, "every retry")] == [1]
    assert query(broken, "every tool error")[0]["key"] == "send_invoice"
    assert query(budget, "first context > 400 tokens")[0]["kind"] == "state"
    assert query(budget, "first context > 100000 tokens") == []
    with pytest.raises(ValueError):
        query(cassette, "__import__('os').system('x')")


def test_explicit_attempt_and_cost_are_features_repeated_calls_are_not() -> None:
    report = run_features(record_failure("transport-timeout"))
    assert report["retry_count"] == 1
    assert report["cost_usd"] == pytest.approx(0.01)
    assert report["tokens"] == {"input_tokens": 40, "output_tokens": 8}
    plain = Session("record")
    plain.mediate("tool", "lookup", {}, lambda: {"ok": True})
    plain.mediate("tool", "lookup", {}, lambda: {"ok": True})
    assert run_features(Cassette(plain.boundaries, plain.chain))["retry_count"] is None


def test_similar_neighbors_stay_inside_the_failure_family() -> None:
    runs = failure_corpus(4)
    target_id, target = "tool-error-0", runs.pop("tool-error-0")
    neighbors = nearest(target, runs, limit=3)
    assert neighbors
    assert all(item["run_id"].startswith("tool-error") for item in neighbors)
    assert neighbors[0]["similarity"] > nearest(target, runs, limit=12)[-1]["similarity"]
    assert target_id not in {item["run_id"] for item in neighbors}


def test_clusters_separate_synthetic_failure_families() -> None:
    pytest.importorskip("sklearn")
    report = cluster_agreement(failure_corpus(6))
    assert report["clusters"] >= 2
    assert report["purity"] == 1.0
    assert report["human_evaluation"] == "not performed"


def test_fresh_failure_names_its_cluster_and_cause() -> None:
    pytest.importorskip("sklearn")
    runs = failure_corpus(4)
    fresh = record_failure("tool-error", 99)
    report = match_failure(fresh, runs, limit=3)
    assert report["likely_cause"] == "tool-error"
    assert report["cluster"] is not None
    assert all(item["run_id"].startswith("tool-error") for item in report["neighbors"])


def test_eval_gate_accepts_the_recorded_policy_and_rejects_a_change() -> None:
    same = policy_gate(500, repeats=1)
    changed = policy_gate(400, repeats=1)
    assert same["passed"]
    assert all(row["replay_pass"] for row in same["cases"])
    assert not changed["passed"]
    assert any(row["changed"] for row in changed["cases"])
    kept = CliRunner().invoke(app, ["eval", "--n", "1", "--budget", "500"])
    shifted = CliRunner().invoke(app, ["eval", "--n", "1", "--budget", "400"])
    assert kept.exit_code == 0, kept.output
    assert json.loads(kept.output)["policy_gate"]["passed"] is True
    assert shifted.exit_code == 1
    assert json.loads(shifted.output)["policy_gate"]["passed"] is False


def test_classifier_beats_majority_baseline_on_grouped_labels() -> None:
    pytest.importorskip("sklearn")
    from flightrecorder.fleet import train_classifier
    from flightrecorder.month5 import classifier_rows

    report = train_classifier(classifier_rows(12))
    learned = report["test"]["macro avg"]["f1-score"]
    assert learned > report["majority_baseline_macro_f1"]
    assert "NOT MEASURED" in report["prompted_llm_baseline"]


def test_match_command_reads_the_local_store(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    db = tmp_path / "runs.db"
    store = RunStore(str(db))
    ids = []
    try:
        for family in ("tool-error", "transport-timeout", "context-budget"):
            for index in range(3):
                ids.append(store.save(record_failure(family, index)))
    finally:
        store.close()
    result = CliRunner().invoke(app, ["match", ids[0], "--db", str(db)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["likely_cause"] == "tool-error"
    assert "672-tool" in payload["qualification"]


def test_classifier_fixture_does_not_embed_its_target_label() -> None:
    from flightrecorder.month5 import classifier_rows

    for row in classifier_rows(12):
        assert row["label"] not in row["text"]
        assert "family-" not in row["text"]


def test_blinded_baseline_inputs_are_bound_and_exclude_answers() -> None:
    from flightrecorder.baseline import prepare_inputs
    from flightrecorder.fleet import train_classifier
    from flightrecorder.month5 import classifier_rows

    rows = classifier_rows(12)
    trained = train_classifier(rows)
    public = prepare_inputs(rows, trained)
    assert {r["id"] for r in public["inputs"]} == {r["id"] for r in trained["held_out"]}
    assert all(set(r) == {"id", "text"} for r in public["inputs"])
    assert "expected" not in public and "predicted" not in public
    altered = [dict(row) for row in rows]
    altered[0]["text"] += " changed"
    with pytest.raises(ValueError, match="dataset differs"):
        prepare_inputs(altered, trained)
