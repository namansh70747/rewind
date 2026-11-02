"""Validated hash-prefix search, sequence alignment, and evidence-based weak labels."""

from __future__ import annotations

import math
from dataclasses import asdict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from .boundary import Boundary, Cassette, canon
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
    if a.kind != b.kind:
        return 3.0
    if a.key != b.key:
        return 2.1 if cosine is None else 1.25 + 0.5 * (1 - cosine)
    if canon(a.request) == canon(b.request):
        return 0.0
    return 0.5 + (
        1
        - (
            cosine
            if cosine is not None
            else SequenceMatcher(None, canon(a.request), canon(b.request)).ratio()
        )
    )


def align(
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
    normalized = None
    if vectors is not None:
        left, right = vectors
        if len(left) != n or len(right) != m:
            raise ValueError("embedding count differs from boundary count")
        dimensions = {len(v) for v in left + right}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ValueError("embedding dimensions must be nonempty and equal")

        def unit(v: list[float]) -> list[float]:
            if not all(math.isfinite(x) for x in v):
                raise ValueError("embeddings must be finite")
            norm = math.sqrt(sum(x * x for x in v))
            if not norm:
                raise ValueError("zero embedding vector")
            return [x / norm for x in v]

        normalized = ([unit(v) for v in left], [unit(v) for v in right])

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


def diagnose(a: Cassette, b: Cassette, model_path: Path | None = None) -> dict[str, Any]:
    validate(a)
    validate(b)
    if (len(a.boundaries) + 1) * (len(b.boundaries) + 1) > 1_000_000:
        raise ValueError("alignment exceeds cell budget; narrow the runs or use hash-bisect")
    vectors = None
    if model_path is not None and a.boundaries and b.boundaries:
        from sentence_transformers import SentenceTransformer

        if not model_path.is_dir():
            raise ValueError("alignment requires a local model directory")
        model = SentenceTransformer(str(model_path), local_files_only=True, device="cpu")
        texts = [
            canon([event.kind, event.key, event.request]).decode()
            for event in a.boundaries + b.boundaries
        ]
        encoded = model.encode(texts, normalize_embeddings=True).tolist()
        vectors = (encoded[: len(a.boundaries)], encoded[len(a.boundaries) :])
    rows = []
    first = None
    for i, j in align(a, b, vectors=vectors):
        left = a.boundaries[i] if i is not None else None
        right = b.boundaries[j] if j is not None else None
        label = taxonomy(left, right)
        row = {
            "a": i,
            "b": j,
            "label": label,
            "left": asdict(left) if left else None,
            "right": asdict(right) if right else None,
        }
        rows.append(row)
        if first is None and label != "identical":
            first = row
    return {
        "alignment_method": "structured + local embedding cosine"
        if vectors
        else "structured + lexical",
        "first_difference": first,
        "alignment": rows,
        "output_changed": a.final_output != b.final_output,
        "interpretation": "Weak evidence label, not a causal diagnosis or hallucination proof.",
    }
