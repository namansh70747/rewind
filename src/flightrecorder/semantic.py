"""Explicit NVIDIA embeddings with recording-bound, offline reusable vector caches."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import httpx

from .boundary import canon
from .diagnosis import normalize_vectors
from .difference import decision, logical
from .integrity import validate

if TYPE_CHECKING:
    from .boundary import Cassette

MODEL = "nvidia/nemotron-3.5-embed-1b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/embeddings"


def texts(cassette: Cassette) -> list[str]:
    return [
        canon(list(logical(event)[:3]) if decision(event) else list(logical(event)[:2])).decode()[
            :4000
        ]
        for event in cassette.boundaries
    ]


def _binding(cassette: Cassette) -> dict[str, Any]:
    return {
        "fingerprint": cassette.fingerprint,
        "input_sha256": hashlib.sha256(canon(texts(cassette))).hexdigest(),
    }


def embed_pair(
    a: Cassette,
    b: Cassette,
    api_key: str,
    *,
    model: str = MODEL,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Explicit outbound operation; never called implicitly by replay or bisect.

    Sends canonical boundary inputs (capped at 4,000 characters per event) to
    NVIDIA. Caches exclude keys and input text; treat vectors as private evidence.
    """
    validate(a)
    validate(b)
    if not api_key:
        raise ValueError("configure NVIDIA_API_KEY for explicit embedding capture")
    inputs = texts(a) + texts(b)
    if not inputs:
        raise ValueError("cannot embed two empty recordings")
    unique = list(dict.fromkeys(inputs))
    unique_vectors: list[list[float]] = []
    with httpx.Client(transport=transport, timeout=90) as client:
        for start in range(0, len(unique), 16):
            batch = unique[start : start + 16]
            response = client.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": batch, "input_type": "passage", "truncate": "END"},
            )
            response.raise_for_status()
            rows = response.json().get("data", [])
            if sorted(row.get("index") for row in rows) != list(range(len(batch))):
                raise ValueError("embedding response has missing, duplicate or invalid indices")
            unique_vectors.extend(
                row["embedding"] for row in sorted(rows, key=lambda row: row["index"])
            )
    by_text = dict(zip(unique, unique_vectors, strict=True))
    vectors = [by_text[text] for text in inputs]
    payload = {
        "version": 1,
        "provider": "nvidia",
        "model": model,
        "left": _binding(a),
        "right": _binding(b),
        "vectors": [vectors[: len(a.boundaries)], vectors[len(a.boundaries) :]],
    }
    load_vectors(payload, a, b)
    return payload


def load_vectors(
    data: Any, a: Cassette, b: Cassette
) -> tuple[list[list[float]], list[list[float]]]:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("unsupported embedding cache")
    if not isinstance(data.get("vectors"), list) or len(data["vectors"]) != 2:
        raise ValueError("embedding cache needs two vector lists")
    if data.get("left") == _binding(a) and data.get("right") == _binding(b):
        pair = data["vectors"]
    elif data.get("left") == _binding(b) and data.get("right") == _binding(a):
        pair = list(reversed(data["vectors"]))
    else:
        raise ValueError("embedding cache does not belong to these recording inputs")
    if not isinstance(pair, list) or len(pair) != 2:
        raise ValueError("embedding cache needs two vector lists")
    if any(not isinstance(side, list) for side in pair) or any(
        not isinstance(vector, list) for side in pair for vector in side
    ):
        raise ValueError("embedding cache needs lists of numeric vectors")
    vectors = (pair[0], pair[1])
    # Shared validation rejects invalid counts, dimensions, zero and non-finite vectors.
    normalize_vectors(vectors, len(a.boundaries), len(b.boundaries))
    return vectors
