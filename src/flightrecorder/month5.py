"""Month 5 failure intelligence on supplied recordings.

Synthetic corpora exercise neighbors, clusters, the eval gate and fresh-failure
matching. They are not a substitute for the author's 672-tool production fleet
or a prompted-LLM baseline collected before the held-out answers were known.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .boundary import Cassette, Session
from .inspection import similarity


def record_failure(family: str, variant: int = 0) -> Cassette:
    """Record one synthetic failure. Variant changes payload, not the symptom."""
    session = Session("record")
    if family == "tool-error":
        session.mediate(
            "tool",
            "send_invoice",
            {"invoice": variant},
            lambda: {"ok": False, "error": "rejected"},
        )
        session.mediate(
            "tool",
            "preview_invoice",
            {"invoice": variant},
            lambda: {"ok": True, "value": "draft"},
        )
    elif family == "transport-timeout":
        session.mediate(
            "http",
            "POST /v1/chat",
            {"attempt": 1},
            lambda: {
                "status": 200,
                "cost_usd": 0.01,
                "body": {"json": {"usage": {"prompt_tokens": 40, "completion_tokens": 8}}},
            },
        )
        session.mediate(
            "http",
            "POST /v1/chat",
            {"attempt": 2},
            lambda: {"transport_error": {"type": "ReadTimeout"}, "status": 504, "cost_usd": 0.0},
        )
    elif family == "context-budget":
        tokens = 900 + variant
        session.mediate(
            "state",
            "context",
            {"turn": variant},
            lambda: {"ok": True, "context_tokens": tokens},
        )
        session.mediate(
            "tool",
            "quote",
            {"sku": "fare"},
            lambda: {"ok": True, "price": 900, "status": "over_budget"},
        )
    else:
        raise ValueError(f"unknown failure family: {family}")
    return Cassette(
        session.boundaries,
        session.chain,
        family,
        "synthetic",
        family,
        {"scenario": "month5-failure-v1", "family": family, "simulated": True},
    )


def failure_corpus(per_family: int = 8) -> dict[str, Cassette]:
    """Three symptom families. Identifiers are ``family-index``."""
    if per_family < 3:
        raise ValueError("need at least 3 runs in each family")
    families = ("tool-error", "transport-timeout", "context-budget")
    return {
        f"{family}-{index}": record_failure(family, index)
        for family in families
        for index in range(per_family)
    }


def nearest(target: Cassette, runs: dict[str, Cassette], limit: int = 5) -> list[dict[str, Any]]:
    """Rank other runs by event-feature cosine similarity."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    ranked = sorted(
        ((similarity(target, cassette), run_id) for run_id, cassette in runs.items()),
        reverse=True,
    )
    return [{"run_id": run_id, "similarity": round(score, 4)} for score, run_id in ranked[:limit]]


def cluster_agreement(runs: dict[str, Cassette] | None = None) -> dict[str, Any]:
    """Measure whether HDBSCAN groups the synthetic families together."""
    from .fleet import fleet_map

    runs = failure_corpus() if runs is None else runs
    report = fleet_map(runs)
    grouped: dict[int, Counter[str]] = {}
    noise = 0
    for point in report["points"]:
        cluster = int(point["cluster"])
        family = str(point["id"]).rsplit("-", 1)[0]
        if cluster < 0:
            noise += 1
            continue
        grouped.setdefault(cluster, Counter())[family] += 1
    assigned = sum(sum(counts.values()) for counts in grouped.values())
    pure = sum(counts.most_common(1)[0][1] for counts in grouped.values())
    return {
        "runs": len(runs),
        "clusters": len(grouped),
        "noise": noise,
        "purity": (pure / assigned) if assigned else 0.0,
        "members": {str(cluster): dict(counts) for cluster, counts in sorted(grouped.items())},
        "human_evaluation": "not performed",
        "qualification": "Synthetic symptom families, not a reviewed production corpus.",
    }


def match_failure(target: Cassette, runs: dict[str, Cassette], limit: int = 5) -> dict[str, Any]:
    """Name the similarity-weighted cluster and weak label of nearby runs."""
    from .fleet import fleet_map, weak_labels

    if not runs:
        raise ValueError("need other saved runs to match against")
    neighbors = nearest(target, runs, limit)
    cluster = None
    if len(runs) >= 3:
        points = {point["id"]: int(point["cluster"]) for point in fleet_map(runs)["points"]}
        cluster_votes: dict[int, float] = {}
        for item in neighbors:
            cluster_id = points.get(item["run_id"], -1)
            if cluster_id >= 0 and item["similarity"] > 0:
                cluster_votes[cluster_id] = cluster_votes.get(cluster_id, 0.0) + float(
                    item["similarity"]
                )
        if cluster_votes:
            cluster = max(cluster_votes, key=cluster_votes.__getitem__)
    causes: dict[str, float] = {}
    for item in neighbors:
        weight = float(item["similarity"])
        if weight <= 0:
            continue
        for label in weak_labels(runs[item["run_id"]]):
            causes[label] = causes.get(label, 0.0) + weight
    if not causes:
        for label in weak_labels(target):
            causes[label] = causes.get(label, 0.0) + 1.0
    return {
        "cluster": cluster,
        "likely_cause": max(causes, key=causes.__getitem__) if causes else None,
        "cause_votes": {label: round(weight, 4) for label, weight in causes.items()},
        "neighbors": neighbors,
        "qualification": (
            "Neighbor majority on the supplied recordings. "
            "Not evidence from a 672-tool production fleet."
        ),
    }


def classifier_rows(per_family: int = 30) -> list[dict[str, str]]:
    """Reviewed-style rows for the synthetic families. Groups do not share text."""
    from .fleet import feature_text

    rows = []
    for family in ("tool-error", "transport-timeout", "context-budget"):
        for index in range(per_family):
            cassette = record_failure(family, index)
            rows.append(
                {
                    "text": f"{feature_text(cassette)} sample-{index}",
                    "label": family,
                    "group": f"{family}-{index}",
                }
            )
    return rows


def policy_gate(candidate_budget: int, repeats: int = 2) -> dict[str, Any]:
    """Replay recorded budget fixtures, then reject a policy that changes outcomes.

    Replay does not call a model. The candidate budget is applied to the recorded
    price, so a prompt or policy edit is caught before it ships.
    """
    from .demo import BUDGET, make_demo_run, record_demo
    from .replay import verify

    if repeats < 1:
        raise ValueError("number of replays must be at least 1")
    rows = []
    for price in (420, 499, 500, 501, 720):
        cassette = record_demo(price)
        result = verify(cassette, make_demo_run(price), repeats)
        recorded = json.loads(cassette.final_output)["status"]
        candidate = "confirmed" if price <= candidate_budget else "over_budget"
        rows.append(
            {
                "price": price,
                "replay_pass": result.passed,
                "recorded_status": recorded,
                "candidate_status": candidate,
                "changed": recorded != candidate,
            }
        )
    return {
        "recorded_budget": BUDGET,
        "candidate_budget": candidate_budget,
        "cases": rows,
        "passed": all(row["replay_pass"] and not row["changed"] for row in rows),
        "note": "Zero model calls. A changed budget is a deterministic fixture diff.",
    }
