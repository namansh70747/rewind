"""Blinded baseline inputs: inference never receives held-out answers or predictions."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def prepare_inputs(samples: list[dict[str, str]], report: dict[str, Any]) -> dict[str, Any]:
    """Bind baseline inputs to the exact dataset and classifier test IDs.

    Export this file to a baseline runner, keep the classifier report/answers local,
    collect predictions, and only then call compare_baseline. This preserves what
    was disclosed; it cannot independently prove the operator never saw answers.
    """
    digest = hashlib.sha256(json.dumps(samples, sort_keys=True).encode()).hexdigest()
    if digest != report.get("dataset_sha256"):
        raise ValueError("dataset differs from the classifier report")
    texts = {}
    for sample in samples:
        identity = hashlib.sha256(
            json.dumps([str(sample["group"]), str(sample["text"])]).encode()
        ).hexdigest()
        if identity in texts:
            raise ValueError("duplicate sample identity")
        texts[identity] = sample["text"]
    held_out = report.get("held_out", [])
    ids = [row["id"] for row in held_out]
    if not ids or len(set(ids)) != len(ids) or any(i not in texts for i in ids):
        raise ValueError("held-out IDs must identify unique dataset rows")
    public = {
        "schema": "rewind.baseline-inputs.v1",
        "dataset_sha256": digest,
        "labels": sorted({s["label"] for s in samples}),
        "inputs": [{"id": i, "text": texts[i]} for i in ids],
        "instructions": "Predict one taxonomy label for each ID from its event features. Return predictions only; do not use expected labels or classifier predictions.",
    }
    public["inputs_sha256"] = hashlib.sha256(
        json.dumps(public["inputs"], sort_keys=True).encode()
    ).hexdigest()
    return public
