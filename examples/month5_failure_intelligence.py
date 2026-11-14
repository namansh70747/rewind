"""Run the Month 5 synthetic failure-intelligence checks. No network and no model calls.

This does not close the real 672-tool fleet gate or the prompted-LLM comparison.
"""

from __future__ import annotations

import json

from flightrecorder.fleet import train_classifier
from flightrecorder.month5 import (
    classifier_rows,
    cluster_agreement,
    failure_corpus,
    match_failure,
    nearest,
    policy_gate,
    record_failure,
)
from flightrecorder.query import query


def main() -> None:
    runs = failure_corpus(8)
    target = runs.pop("tool-error-0")
    learned = train_classifier(classifier_rows(12))
    report = {
        "corpus_runs": len(runs) + 1,
        "neighbors": nearest(target, runs, limit=5),
        "clusters": cluster_agreement({**runs, "tool-error-0": target}),
        "fresh_failure": match_failure(record_failure("transport-timeout", 50), runs, limit=5),
        "tool_errors": len(query(record_failure("tool-error"), "every tool error")),
        "classifier_macro_f1": learned["test"]["macro avg"]["f1-score"],
        "majority_baseline_macro_f1": learned["majority_baseline_macro_f1"],
        "prompted_llm_baseline": learned["prompted_llm_baseline"],
        "recorded_policy_gate": policy_gate(500, repeats=1)["passed"],
        "changed_policy_gate": policy_gate(400, repeats=1)["passed"],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
