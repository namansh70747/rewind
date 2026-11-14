"""Validated hash-prefix search, sequence alignment, and evidence-based weak labels."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from .boundary import Boundary, Cassette, canon
from .difference import decision, json_diff, logical, similarity, values_named
from .integrity import validate


def hash_bisect(a: Cassette, b: Cassette) -> int | None:
    """Validate O(N), then find first unequal chain link in O(log N) comparisons."""
    validate(a)
    validate(b)
    if a.chain_algorithm != b.chain_algorithm:
        raise ValueError("chain algorithms differ; use aligned comparison")
    low, high = 0, min(len(a.boundaries), len(b.boundaries))
    while low < high:
        middle = (low + high) // 2
        if a.boundaries[middle].chain_hash == b.boundaries[middle].chain_hash:
            low = middle + 1
        else:
            high = middle
    if low < min(len(a.boundaries), len(b.boundaries)) or len(a.boundaries) != len(b.boundaries):
        return low
    return low if a.final_output != b.final_output else None


def _cost(a: Boundary, b: Boundary, cosine: float | None = None) -> float:
    ak, an, ar, _, ap = logical(a)
    bk, bn, br, _, bp = logical(b)
    if ak != bk or ap != bp:
        return 3.0
    semantic = 1 - cosine if cosine is not None else 1 - similarity(ar, br)
    if an != bn:
        return 1.25 + 0.25 * semantic
    if canon(ar) == canon(br):
        return 0.0
    return 0.25 + 0.5 * (1 - similarity(ar, br)) + 0.25 * semantic


def normalize_vectors(
    vectors: tuple[list[list[float]], list[list[float]]], n: int, m: int
) -> tuple[list[list[float]], list[list[float]]]:
    left, right = vectors
    if len(left) != n or len(right) != m:
        raise ValueError("embedding count differs from boundary count")
    dimensions = {len(v) for v in left + right}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("embedding dimensions must be nonempty and equal")

    def unit(v: list[float]) -> list[float]:
        if not all(type(x) in (int, float) and math.isfinite(x) for x in v):
            raise ValueError("embeddings must be finite")
        scale = max(abs(x) for x in v)
        if not scale:
            raise ValueError("zero embedding vector")
        norm = math.sqrt(sum((x / scale) ** 2 for x in v))
        return [(x / scale) / norm for x in v]

    return ([unit(v) for v in left], [unit(v) for v in right])


def _align_suffix(
    a: Cassette,
    b: Cassette,
    max_cells: int = 1_000_000,
    vectors: tuple[list[list[float]], list[list[float]]] | None = None,
) -> list[tuple[int | None, int | None]]:
    """Needleman-Wunsch global alignment with structured input similarity.

    Response differences do not affect alignment, preventing a changed decision
    from being mistaken for an inserted event. Lexical similarity is not embeddings.
    """
    n, m = len(a.boundaries), len(b.boundaries)
    if (n + 1) * (m + 1) > max_cells:
        raise ValueError("alignment exceeds cell budget; narrow the runs or use hash-bisect")
    normalized = normalize_vectors(vectors, n, m) if vectors is not None else None

    def cost(i: int, j: int) -> float:
        cosine = None
        if normalized is not None:
            cosine = max(
                -1.0,
                min(
                    1.0, sum(x * y for x, y in zip(normalized[0][i], normalized[1][j], strict=True))
                ),
            )
        return _cost(a.boundaries[i], b.boundaries[j], cosine)

    grid = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        grid[i][0] = float(i)
    for j in range(m + 1):
        grid[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            grid[i][j] = min(
                grid[i - 1][j] + 1,
                grid[i][j - 1] + 1,
                grid[i - 1][j - 1] + cost(i - 1, j - 1),
            )
    path: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i or j:
        if i and j and abs(grid[i][j] - (grid[i - 1][j - 1] + cost(i - 1, j - 1))) < 1e-9:
            path.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i and abs(grid[i][j] - (grid[i - 1][j] + 1)) < 1e-9:
            path.append((i - 1, None))
            i -= 1
        else:
            path.append((None, j - 1))
            j -= 1
    return list(reversed(path))


def align(
    a: Cassette,
    b: Cassette,
    max_cells: int = 1_000_000,
    vectors: tuple[list[list[float]], list[list[float]]] | None = None,
) -> list[tuple[int | None, int | None]]:
    """Anchor the identical observed prefix before global suffix alignment.

    Identical repeated calls can have ambiguous insertion occurrence identity;
    preserve the earliest shared evidence rather than shifting a known prefix.
    """
    if vectors is not None:
        normalize_vectors(vectors, len(a.boundaries), len(b.boundaries))
    prefix = 0
    for left, right in zip(a.boundaries, b.boundaries, strict=False):
        if canon([left.kind, left.key, left.request, left.response]) != canon(
            [right.kind, right.key, right.request, right.response]
        ):
            break
        prefix += 1
    path: list[tuple[int | None, int | None]] = [(i, i) for i in range(prefix)]
    if prefix == len(a.boundaries) == len(b.boundaries):
        return path
    suffix_vectors = (vectors[0][prefix:], vectors[1][prefix:]) if vectors is not None else None
    suffix = _align_suffix(
        Cassette(boundaries=a.boundaries[prefix:]),
        Cassette(boundaries=b.boundaries[prefix:]),
        max_cells=max_cells,
        vectors=suffix_vectors,
    )
    return path + [
        (i + prefix if i is not None else None, j + prefix if j is not None else None)
        for i, j in suffix
    ]


def taxonomy(a: Boundary | None, b: Boundary | None) -> str:
    if a is None or b is None:
        return "step-inserted" if a is None else "step-removed"
    if a.kind != b.kind or a.key != b.key:
        return "tool-choice" if "tool" in (a.kind, b.kind) else "boundary-choice"
    if canon(a.request) != canon(b.request):
        return "argument-drift" if a.kind == "tool" else "input-drift"
    if canon(a.response) != canon(b.response):
        return {
            "tool": "tool-result-drift",
            "llm": "sampling-or-model-drift",
            "http": "provider-response-drift",
            "rng": "randomness-drift",
        }.get(a.kind, "value-drift")
    return "identical"


def _category(left: Boundary | None, right: Boundary | None, label: str) -> tuple[str, str]:
    if left is None or right is None:
        return label, "A recorded step was added or removed."
    kind, key, request, response, _ = logical(left)
    rk, rkey, other_request, other_response, _ = logical(right)
    if kind != rk or key != rkey:
        return "tool-choice", "The selected tool or boundary changed."
    if canon(request) != canon(other_request):
        return (
            "arg-hallucination" if kind in {"tool", "mcp"} else "input-drift",
            "The request arguments already differ; inspect earlier decisions or task inputs. Argument drift alone is not proof of hallucination.",
        )
    if canon(response) == canon(other_response):
        return "metadata-only", "Raw metadata differs, but the logical decision values match."
    finish = values_named(other_response, {"finish_reason", "stop_reason"})
    if any(value in ("length", "max_tokens", "max_output_tokens") for value in finish):
        return "truncation", "The candidate reports a token-limit stop."
    cost_a = values_named(response, {"cost", "total_cost"})
    cost_b = values_named(other_response, {"cost", "total_cost"})
    if (
        cost_a
        and cost_b
        and type(cost_a[0]) in (int, float)
        and type(cost_b[0]) in (int, float)
        and cost_a[0] > 0
        and cost_b[0] > 2 * cost_a[0]
    ):
        return "cost-blowup", "Recorded cost increased by more than 2x."
    if kind in {"tool", "mcp"}:
        if any(word in key.casefold() for word in ("search", "retriev", "vector")):
            return "retrieval-drift", "The same retrieval request returned different evidence."
        return "tool-result-drift", "The same tool input returned a different result."
    if kind in {"http", "llm"}:
        return (
            "sampling-flake",
            "The same model input returned different output; sampling, model changes or provider behavior are candidates, not proven causes.",
        )
    return label, "The recorded value changed."


def diagnose(
    a: Cassette,
    b: Cassette,
    model_path: Path | None = None,
    *,
    vectors: tuple[list[list[float]], list[list[float]]] | None = None,
    method: str = "auto",
) -> dict[str, Any]:
    validate(a)
    validate(b)
    if method not in {"auto", "hash", "align"}:
        raise ValueError("method must be auto, hash or align")
    if vectors is not None and model_path is not None:
        raise ValueError("choose a local model or cached vectors, not both")
    if model_path is not None and a.boundaries and b.boundaries:
        from sentence_transformers import SentenceTransformer

        if not model_path.is_dir():
            raise ValueError("alignment requires a local model directory")
        model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
        texts = [canon(list(logical(e)[:3])).decode() for e in a.boundaries + b.boundaries]
        encoded = model.encode(texts, normalize_embeddings=True).tolist()
        vectors = (encoded[: len(a.boundaries)], encoded[len(a.boundaries) :])
    keys_a = [(e.kind, e.key) for e in a.boundaries]
    keys_b = [(e.kind, e.key) for e in b.boundaries]
    same_shape = keys_a == keys_b and a.chain_algorithm == b.chain_algorithm
    same_inputs = same_shape and all(
        canon(x.request) == canon(y.request)
        for x, y in zip(a.boundaries, b.boundaries, strict=True)
    )
    unambiguous = same_inputs or (same_shape and len(set(keys_a)) == len(keys_a))
    use_hash = same_shape and (
        method == "hash" or (method == "auto" and unambiguous and vectors is None)
    )
    if method == "hash" and not same_shape:
        raise ValueError(
            "hash comparison requires aligned kind/key sequences and the same chain algorithm"
        )
    path: list[tuple[int | None, int | None]]
    if use_hash:
        path = [(i, i) for i in range(len(a.boundaries))]
        low, high, comparisons = 0, len(a.boundaries), 0
        while low < high:
            middle = (low + high) // 2
            comparisons += 1
            if a.boundaries[middle].chain_hash == b.boundaries[middle].chain_hash:
                low = middle + 1
            else:
                high = middle
        first_hash = low if low < len(a.boundaries) or a.final_output != b.final_output else None
    else:
        path = align(a, b, vectors=vectors)
        first_hash, comparisons = None, 0
    rows, first, first_decision = [], None, None
    for i, j in path:
        left = a.boundaries[i] if i is not None else None
        right = b.boundaries[j] if j is not None else None
        label = taxonomy(left, right)
        category, summary = _category(left, right, label)
        if (
            left is None
            and right is not None
            and j is not None
            and any(logical(prior)[:3] == logical(right)[:3] for prior in b.boundaries[:j])
        ):
            category, summary = "loop", "A matching tool request is repeated."
        raw_left, raw_right = asdict(left) if left else None, asdict(right) if right else None
        relevant = (left is not None and decision(left)) or (right is not None and decision(right))
        logical_changed = (
            left is None or right is None or canon(logical(left)) != canon(logical(right))
        )
        row = {
            "a": i,
            "b": j,
            "label": label,
            "category": category,
            "summary": summary,
            "left": raw_left,
            "right": raw_right,
            "decision_difference": bool(label != "identical" and relevant and logical_changed),
            "input_relation": "same-input"
            if left and right and canon(logical(left)[:3]) == canon(logical(right)[:3])
            else "different-input-or-gap",
            "raw_diff": json_diff(raw_left, raw_right) if label != "identical" else [],
        }
        rows.append(row)
        if first is None and label != "identical":
            first = row
        if first_decision is None and row["decision_difference"]:
            first_decision = row
    if first is None and a.final_output != b.final_output:
        first = {
            "a": None,
            "b": None,
            "label": "final-output-drift",
            "category": "agent-logic-drift",
            "summary": "Boundary values match but final outputs differ; inspect agent logic.",
            "left": {"final_output": a.final_output},
            "right": {"final_output": b.final_output},
            "raw_diff": json_diff(a.final_output, b.final_output),
        }
    primary = first_decision or first
    prior = None
    if primary in rows and rows.index(primary) > 0:
        preceding = rows[rows.index(primary) - 1]
        prior = {"a": preceding["a"], "b": preceding["b"], "label": preceding["label"]}
    return {
        "comparison_method": "hash-chain" if use_hash else "sequence-alignment",
        "alignment_method": (
            "structured + embedding cosine" if vectors else "structured + lexical"
        ),
        "first_difference": first,
        "first_diverging_decision": first_decision,
        "primary_difference": primary,
        "alignment": rows,
        "hash_search": {
            "first_boundary": first_hash,
            "comparisons": comparisons,
            "validation_boundaries": len(a.boundaries) + len(b.boundaries),
            "complexity": "O(N) validation and report; O(log N) hash comparisons",
        },
        "upstream_context": prior,
        "output_changed": a.final_output != b.final_output,
        "interpretation": "Observed differences and weak candidate labels, not proven root cause. Inspect raw evidence and task/code provenance.",
        "human_review": "required for root-cause agreement",
    }
