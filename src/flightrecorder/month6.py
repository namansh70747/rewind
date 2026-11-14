"""Month 6 — LoRA explainer stub, concurrent replay, GC/retention, and release hardening.

Weeks 23-26 of the six-month roadmap (P5).  No model-training claim is made;
the LoRA fine-tuning path is documented in ADR-0005 and ADR-0014 and will be
activated only when a reviewed, labeled corpus exists.  The explainer delivered
here builds plain-English narration from the classifier's label, the cluster's
top evidence features, and the bisect divergence class — deterministically, with
no model calls and no hallucinated prose.

Design decisions
-----------------
* ``explain``      — single entry-point for plain-English root-cause narration.
* ``retention_gc`` — delete runs older than a retention window plus orphaned blobs.
* ``concurrent_replay`` — replay a cassette N times in parallel using threads.
* ``benchmark``    — measure replay throughput; no fabricated numbers.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .boundary import Cassette

# ---------------------------------------------------------------------------
# Narration templates — deterministic; no model calls
# ---------------------------------------------------------------------------

_CAUSE_SENTENCES: dict[str, str] = {
    "tool-error": "A tool-error label was suggested. Inspect the recorded tool response and error/status fields before attributing a cause.",
    "transport-timeout": "A transport-timeout label was suggested. Inspect captured transport errors and explicit attempts; retry failure is not implied without terminal evidence.",
    "context-budget": "A context/budget-related symptom was suggested. Compare recorded tokens with an explicitly configured limit; a token count alone does not prove overflow.",
    "arg-hallucination": "Changed request arguments were suggested. Argument drift alone is not proof of hallucination; inspect task inputs and earlier decisions.",
    "tool-choice": "A changed tool choice was suggested. Compare aligned tool identities; this need not be an inserted or deleted step.",
    "sampling-flake": "Model-output drift was suggested. Sampling, model changes and provider behavior are alternative explanations; randomness is not a proven cause.",
    "tool-result-drift": "A changed tool result was suggested. Compare baseline and candidate responses for identical inputs; offline replay itself should reproduce its recording exactly.",
    "retrieval-drift": "Changed retrieval evidence was suggested. Compare results for identical retrieval requests before attributing downstream behavior.",
    "loop": "Repeated requests were suggested. Inspect their arguments and progress; repetition alone does not prove an infinite loop.",
    "cost-blowup": "A cost or token increase was suggested. Inspect measured costs and the configured budget; missing measurements cannot establish an overrun.",
    "truncation": "A token-limit stop was suggested. Inspect the recorded finish/stop reason; a short answer alone does not establish truncation.",
    "api-error": "An API-error label was suggested. Inspect recorded HTTP status and response evidence; credentials or rate limits are possible causes, not established facts.",
}

_DEFAULT_SENTENCE = (
    "The classifier assigned label '{label}'.  Review the recorded timeline "
    "in `fr show` and the cluster evidence for details.  No automated causal "
    "narrative is available for this label."
)

_NEXT_STEPS: dict[str, list[str]] = {
    "tool-error": [
        "Run `fr show <run_id>` and inspect the tool boundary at the first error seq.",
        "Check the tool's error field and status code in the recorded response.",
        "Consider adding a retry policy or input validation upstream of the tool.",
    ],
    "transport-timeout": [
        "Run `fr query <run_id> 'every retry'` to list the retried boundaries.",
        "Check the recorded endpoint and attempt count in the boundary request.",
        "Tune the HTTP timeout or add a circuit-breaker for this provider.",
    ],
    "context-budget": [
        "Run `fr query <run_id> 'first context > 0 tokens'` to find the overflow.",
        "Reduce system-prompt size or summarize earlier turns before they accumulate.",
        "Use `fr eval-fixtures` to gate a changed budget before it ships.",
    ],
}

_DEFAULT_STEPS = [
    "Run `fr show <run_id>` to inspect the recorded timeline.",
    "Run `fr diagnose <passing_run> <failing_run>` to align two runs.",
    "Run `fr match <run_id>` to find similar recorded failures.",
]


def _cause_sentence(label: str) -> str:
    return _CAUSE_SENTENCES.get(label, _DEFAULT_SENTENCE.format(label=label))


def _next_steps(label: str) -> list[str]:
    return _NEXT_STEPS.get(label, _DEFAULT_STEPS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain(
    cassette: Cassette,
    *,
    classifier_report: dict[str, Any] | None = None,
    cluster_report: dict[str, Any] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Produce a plain-English root-cause explanation from recorded evidence.

    This function is deterministic: it never calls a model and never fabricates
    prose.  Every sentence comes from a fixed template keyed on the classifier
    label or the cassette's divergence_class metadata.

    Parameters
    ----------
    cassette:
        The recorded run to explain.
    classifier_report:
        Optional output of ``fleet.train_classifier`` / ``fleet.predict_cause``.
        When supplied, its ``label`` and ``probabilities`` are shown.
    cluster_report:
        Optional output of ``fleet.fleet_map``.  When supplied, the top features
        from the matching cluster's members are embedded in the explanation.
    run_id:
        Human-readable identifier for the ``next_steps`` suggestions.
    """
    from .fleet import weak_labels
    from .run_features import run_features

    features_report = run_features(cassette)

    # Determine the best available label, in preference order:
    # 1. classifier prediction (reviewed model output)
    # 2. divergence_class metadata set by bisect
    # 3. most-voted weak label
    # 4. cassette label (may be "synthetic")
    label: str | None = None
    probability: float | None = None
    label_source = "none"

    if classifier_report and isinstance(classifier_report.get("label"), str):
        label = classifier_report["label"]
        probs = classifier_report.get("probabilities", {})
        probability = probs.get(label)
        label_source = "classifier"
    elif isinstance(features_report.get("divergence_class"), str):
        label = features_report["divergence_class"]
        label_source = "bisect-metadata"
    else:
        votes = weak_labels(cassette)
        if votes:
            label = votes[0]
            label_source = "weak-label"
        family = cassette.metadata.get("family")
        if isinstance(family, str) and family != "synthetic":
            label = family
            label_source = "metadata-family"

    cause_text = _cause_sentence(label or "unknown")
    steps = _next_steps(label or "unknown")
    if run_id:
        steps = [s.replace("<run_id>", run_id) for s in steps]

    # Embed top cluster evidence features if a cluster report is provided.
    top_features: list[str] = []
    if cluster_report and isinstance(cluster_report.get("points"), list):
        # Find which cluster this cassette's run_id belongs to (if any).
        cluster_id: int | None = None
        for point in cluster_report["points"]:
            if point.get("id") == run_id:
                cluster_id = int(point["cluster"]) if point["cluster"] >= 0 else None
                break
        if cluster_id is not None:
            # Collect member run_ids from the same cluster.
            member_ids = {
                p["id"] for p in cluster_report["points"] if int(p["cluster"]) == cluster_id
            }
            # Use the timelines block if present (embedded in exploration_data).
            timelines = cluster_report.get("timelines", {})
            from collections import Counter

            counts: Counter[str] = Counter()
            for mid in member_ids:
                tl = timelines.get(mid, {})
                for event in tl.get("events", []):
                    key = event.get("key", "")
                    if key:
                        counts[str(key)] += 1
            top_features = [k for k, _ in counts.most_common(5)]

    return {
        "schema": "rewind.explain.v1",
        "run_id": run_id or cassette.fingerprint[:16],
        "label": label,
        "label_source": label_source,
        "probability": round(probability, 4) if probability is not None else None,
        "cause": cause_text,
        "top_cluster_features": top_features,
        "next_steps": steps,
        "feature_summary": {
            "boundary_count": features_report["boundary_count"],
            "tool_histogram": features_report.get("tool_histogram"),
            "retry_count": features_report.get("retry_count"),
            "cost_usd": features_report.get("cost_usd"),
        },
        "qualification": (
            "Narration is a candidate explanation keyed on a supplied or weak label; template determinism does not establish factual grounding. "
            "No model is called.  Causal attribution requires human review of the "
            "recorded timeline.  LoRA fine-tuning is deferred to a later phase "
            "(ADR-0005, ADR-0014); this stub is its documented placeholder."
        ),
        "lora_status": "deferred — labeled corpus and training harness not yet available",
    }


# ---------------------------------------------------------------------------
# Concurrent replay
# ---------------------------------------------------------------------------


@dataclass
class ConcurrentReplayResult:
    """Outcome of a concurrent N-way replay."""

    n: int
    passed: int
    failed: int
    elapsed_s: float
    throughput_replays_per_s: float
    errors: list[str]

    def __str__(self) -> str:
        return (
            f"concurrent replay: {self.passed}/{self.n} passed "
            f"({self.failed} failed) in {self.elapsed_s:.2f}s "
            f"[{self.throughput_replays_per_s:.1f} replays/s]"
        )


def concurrent_replay(
    cassette: Cassette,
    run_fn: Any,
    n: int = 10,
    max_workers: int | None = None,
) -> ConcurrentReplayResult:
    """Replay *cassette* n times in parallel threads and report throughput.

    Parameters
    ----------
    cassette:
        The recorded run to replay.
    run_fn:
        A callable ``(Session, transport) -> str`` — the same signature used
        by ``replay.replay_once``.
    n:
        Number of parallel replays.  Must be ≥ 1.
    max_workers:
        Thread-pool size.  Defaults to ``min(n, 32)``.
    """
    from .replay import replay_once

    if n < 1:
        raise ValueError("n must be at least 1")
    if max_workers is not None and max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    if max_workers is None:
        max_workers = min(n, 32)

    errors: list[str] = []
    passed = 0
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(replay_once, cassette, run_fn) for _ in range(n)]
        for future in concurrent.futures.as_completed(futures):
            exc = future.exception()
            if exc is None:
                output, fingerprint = future.result()
                if output == cassette.final_output and fingerprint == cassette.fingerprint:
                    passed += 1
                else:
                    errors.append("Replay output or fingerprint differs from recording")
            else:
                errors.append(str(exc))

    elapsed = time.perf_counter() - t0
    failed = n - passed
    return ConcurrentReplayResult(
        n=n,
        passed=passed,
        failed=failed,
        elapsed_s=round(elapsed, 3),
        throughput_replays_per_s=round(n / elapsed, 2) if elapsed > 0 else 0.0,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Retention / GC
# ---------------------------------------------------------------------------


@dataclass
class RetentionReport:
    """Summary of a retention sweep."""

    runs_deleted: int
    runs_retained: int
    blobs_collected: int

    def __str__(self) -> str:
        return (
            f"retention: deleted {self.runs_deleted} run(s), "
            f"retained {self.runs_retained}, "
            f"collected {self.blobs_collected} orphan blob(s)"
        )


def retention_gc(
    db_path: str,
    *,
    keep_last: int | None = None,
    max_age_days: float | None = None,
    dry_run: bool = False,
) -> RetentionReport:
    """Delete old runs and unreachable blobs from the local store.

    At least one of ``keep_last`` or ``max_age_days`` must be specified.

    Parameters
    ----------
    db_path:
        Path to the SQLite database (usually ``.rewind/runs.db``).
    keep_last:
        Keep only the most recent *keep_last* runs; delete the rest.
    max_age_days:
        Delete runs whose ``created_at`` timestamp is older than this many days.
    dry_run:
        If ``True``, compute what would be deleted but make no changes.
    """
    from datetime import UTC, datetime, timedelta

    if keep_last is None and max_age_days is None:
        raise ValueError("specify keep_last or max_age_days (or both)")
    if keep_last is not None and keep_last < 0:
        raise ValueError("keep_last must be non-negative")
    if max_age_days is not None and max_age_days <= 0:
        raise ValueError("max_age_days must be positive")

    from .store import RunStore

    store = RunStore(db_path)
    try:
        summaries = list(store.list_runs())
        # Sort newest-first.
        summaries.sort(key=lambda s: s.created_at, reverse=True)

        to_delete: list[str] = []

        if keep_last is not None:
            to_delete.extend(s.id for s in summaries[keep_last:])

        if max_age_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
            for s in summaries:
                if s.id in to_delete:
                    continue
                try:
                    ts = datetime.fromisoformat(s.created_at)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts < cutoff:
                        to_delete.append(s.id)
                except ValueError:
                    continue  # unparseable timestamp — skip

        retained = len(summaries) - len(to_delete)

        if not dry_run:
            conn = store.conn
            with conn:
                for run_id in to_delete:
                    conn.execute("DELETE FROM boundary WHERE run_id = ?", (run_id,))
                    conn.execute("DELETE FROM run_metadata WHERE run_id = ?", (run_id,))
                    conn.execute("DELETE FROM snapshot WHERE run_id = ?", (run_id,))
                    conn.execute("DELETE FROM run WHERE id = ?", (run_id,))

        blobs_collected = 0 if dry_run else store.garbage_collect()

        return RetentionReport(
            runs_deleted=len(to_delete),
            runs_retained=retained,
            blobs_collected=blobs_collected,
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def benchmark_replay(
    cassette: Cassette,
    run_fn: Any,
    n: int = 20,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Measure replay throughput and return a structured evidence record.

    No timing claim is made without an actual run; fabricated numbers are
    explicitly excluded.  Call this on a real cassette to produce evidence.
    """
    if n < 1 or max_workers < 1:
        raise ValueError("n and max_workers must each be at least 1")

    result = concurrent_replay(cassette, run_fn, n=n, max_workers=max_workers)
    return {
        "schema": "rewind.benchmark.v1",
        "n_replays": result.n,
        "passed": result.passed,
        "failed": result.failed,
        "elapsed_s": result.elapsed_s,
        "throughput_replays_per_s": result.throughput_replays_per_s,
        "max_workers": max_workers,
        "boundaries": len(cassette.boundaries),
        "qualification": (
            "Measured on supplied cassette.  Production throughput depends on "
            "boundary count, payload size, and hardware.  No claim is made without "
            "a run on the target machine."
        ),
    }
