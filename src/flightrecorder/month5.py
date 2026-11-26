"""Month 5 failure intelligence on supplied recordings.

Synthetic corpora exercise neighbors, clusters, the eval gate and fresh-failure
matching. The proposed course substitute uses synthetic runs and an honest keyword
baseline; approval remains pending (ADR-0015). That is not the original 672-tool production fleet.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    """Synthetic labels derived from scenario construction, without human review."""
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


KEYWORD_STUB_PROMPT = (
    "keyword-stub-v1: if text mentions Timeout/ReadTimeout guess transport-timeout; "
    "if over_budget/context_tokens guess context-budget; else tool-error."
)


def keyword_stub_label(text: str, identity: str, labels: list[str]) -> str:
    """Deterministic Gemini-free baseline used when paid LLM keys are not available."""
    if not labels:
        raise ValueError("need allowed labels")
    ordered = sorted(labels)
    if "ReadTimeout" in text or "transport-timeout" in text or "Timeout" in text:
        guess = "transport-timeout"
    elif "over_budget" in text or "context_tokens" in text:
        guess = "context-budget"
    else:
        guess = "tool-error"
    if guess not in ordered:
        raise ValueError(f"keyword prediction is outside allowed labels: {guess}")
    return guess


LIVE_BASELINE_PROMPT = (
    "Predict one taxonomy label for these agent-run event features. "
    "Reply with exactly one label from the allowed list. No extra words."
)


def _normalize_live_label(text: str, labels: list[str]) -> str:
    lowered = text.strip().lower()
    matches = [label for label in labels if label.lower() == lowered]
    if len(matches) != 1:
        raise ValueError(f"invalid or ambiguous model label: {text!r}")
    return matches[0]


def live_prompted_predictions(
    inputs: dict[str, Any], provider_name: str | None = None
) -> dict[str, Any]:
    """Collect an explicitly requested prompted baseline; missing credentials fail."""
    import httpx

    from .providers import PROVIDERS

    if provider_name is not None and provider_name not in {"gemini", "nvidia"}:
        raise ValueError("baseline provider must be gemini or nvidia")
    order = [provider_name] if provider_name else ["gemini", "nvidia"]
    chosen = None
    for name in order:
        if not name or name not in PROVIDERS:
            continue
        spec = PROVIDERS[name]
        if os.environ.get(spec.key_env):
            chosen = spec
            break
    if chosen is None:
        raise ValueError("live baseline requires Gemini or NVIDIA credentials")
    labels = list(inputs["labels"])
    prompt_text = LIVE_BASELINE_PROMPT + " Allowed: " + ", ".join(sorted(labels))
    rows = []
    with httpx.Client(timeout=120, trust_env=False) as client:
        for item in inputs["inputs"]:
            response = client.post(
                chosen.url,
                headers=chosen.headers(os.environ.get(chosen.key_env, "")),
                json=chosen.body(
                    chosen.default_model,
                    [{"role": "user", "content": prompt_text + "\n" + str(item["text"])}],
                ),
            )
            response.raise_for_status()
            rows.append(
                {
                    "id": item["id"],
                    "label": _normalize_live_label(chosen.extract(response.json()), labels),
                }
            )
    return {
        "predictions": rows,
        "provenance": {
            "provider": chosen.name,
            "model": chosen.default_model,
            "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        },
    }


def keyword_stub_predictions(inputs: dict[str, Any]) -> dict[str, Any]:
    labels = list(inputs["labels"])
    rows = [
        {
            "id": item["id"],
            "label": keyword_stub_label(str(item["text"]), str(item["id"]), labels),
        }
        for item in inputs["inputs"]
    ]
    return {
        "predictions": rows,
        "provenance": {
            "provider": "course-substitute-heuristic",
            "model": "keyword-baseline-v2",
            "prompt_sha256": hashlib.sha256(KEYWORD_STUB_PROMPT.encode()).hexdigest(),
        },
    }


def close_month5_gates(per_family: int = 10, live: bool = False) -> dict[str, Any]:
    """Run the course Month 5 close: substitute fleet, match, clusters, Gemini/NVIDIA baseline."""
    from .baseline import prepare_inputs
    from .fleet import compare_baseline, train_classifier

    if per_family < 8:
        raise ValueError("need at least 8 runs per family")
    corpus = failure_corpus(per_family)
    fresh_id = "tool-error-fresh"
    fresh = record_failure("tool-error", 90)
    others = {key: value for key, value in corpus.items() if key != "tool-error-0"}
    samples = classifier_rows(12)
    learned = train_classifier(samples)
    blinded = prepare_inputs(samples, learned)
    baseline = live_prompted_predictions(blinded) if live else keyword_stub_predictions(blinded)
    compared = compare_baseline(learned, baseline)
    clusters = cluster_agreement(corpus)
    matched = match_failure(fresh, others, limit=5)
    return {
        "schema": "rewind.month5-course-close.v1",
        "substitute_fleet_runs": len(corpus),
        "families": ["tool-error", "transport-timeout", "context-budget"],
        "neighbors": nearest(corpus["tool-error-0"], others, limit=5),
        "clusters": clusters,
        "fresh_failure": {**matched, "run_id": fresh_id},
        "policy_gate_recorded": policy_gate(500, repeats=1)["passed"],
        "policy_gate_changed": policy_gate(400, repeats=1)["passed"],
        "classifier_macro_f1": learned["test"]["macro avg"]["f1-score"],
        "majority_baseline_macro_f1": learned["majority_baseline_macro_f1"],
        "heuristic_baseline": compared,
        "baseline_source": baseline["provenance"]["model"],
        "human_evaluation": "not performed",
        "course_approval": "pending",
        "qualification": (
            "Synthetic substitute proposal (ADR-0015), pending course approval. "
            "Does not satisfy the original real-fleet or human-review gates. "
            "Offline keyword comparison is not a prompted-LLM baseline. "
            "Live baseline requires explicit opt-in and credentials."
        ),
    }
