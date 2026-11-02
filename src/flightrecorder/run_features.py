"""Versioned, evidence-only per-run feature export for fleet analysis."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from .integrity import validate
from .redaction import redact

if TYPE_CHECKING:
    from .boundary import Cassette


def run_features(cassette: Cassette) -> dict[str, Any]:
    """Extract explicit metadata; repeated calls alone never establish a retry.

    Token totals cover non-stream JSON responses with usage fields. Stream-only
    usage and prices are not inferred. Missing measurements remain null.
    """
    validate(cassette)
    tools: Counter[str] = Counter()
    finishes: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    tokens: Counter[str] = Counter()
    usage_boundaries = 0
    for b in cassette.boundaries:
        kinds[b.kind] += 1
        response = b.response
        kind, key = b.kind, b.key
        request = b.request
        if kind == "async-start":
            continue
        if kind in {"async-result", "async-error", "async-cancel"} and isinstance(b.request, dict):
            # Async events carry their original boundary identity in the request.
            kind = str(b.request.get("kind", kind))
            key = str(b.request.get("key", key))
            request = b.request.get("request", {})
        if kind == "tool" or (kind == "mcp" and key.endswith("/tools/call")):
            if kind == "mcp" and isinstance(request, dict):
                params = request.get("params", {})
                if isinstance(params, dict) and isinstance(params.get("name"), str):
                    key += ":" + params["name"]
            tools[str(redact(key))] += 1
        if not isinstance(response, dict):
            continue
        if isinstance(response.get("status"), (str, int)):
            statuses[str(response["status"])] += 1
        body = response.get("body", {})
        payload = body.get("json", {}) if isinstance(body, dict) else {}
        if not isinstance(payload, dict):
            continue
        usage = payload.get("usage")
        if isinstance(usage, dict):
            found = False
            for target, aliases in {
                "input_tokens": ("input_tokens", "prompt_tokens"),
                "output_tokens": ("output_tokens", "completion_tokens"),
            }.items():
                value = next((usage[name] for name in aliases if name in usage), None)
                if type(value) is int and value >= 0:
                    tokens[target] += value
                    found = True
            usage_boundaries += int(found)
        reasons = [payload.get("stop_reason")]
        choices = payload.get("choices", [])
        if isinstance(choices, list):
            reasons.extend(c.get("finish_reason") for c in choices if isinstance(c, dict))
        for reason in reasons:
            if isinstance(reason, str):
                finishes[str(redact(reason))] += 1
    return {
        "schema": "rewind.run-features.v1",
        "fingerprint": cassette.fingerprint,
        "boundary_count": len(cassette.boundaries),
        "boundary_kinds": dict(sorted(kinds.items())),
        "tool_histogram": dict(sorted(tools.items())),
        "response_statuses": dict(sorted(statuses.items())),
        "finish_reasons": dict(sorted(finishes.items())),
        "tokens": dict(tokens) if usage_boundaries else None,
        "usage_boundaries": usage_boundaries,
        "retry_count": None,
        "cost_usd": None,
        "divergence_class": None,
        "measurement_notes": [
            "Tokens include only captured non-stream JSON usage; absent fields are not zero.",
            "Retries need explicit attempt metadata; repeated calls are not automatically retries.",
            "Cost requires a supplied price schedule; divergence requires a comparison run.",
        ],
    }
