"""Auto-bisect v1 — first diverging decision between two recordings."""

from __future__ import annotations

import copy

from flightrecorder import Cassette, first_divergence
from flightrecorder.boundary import Boundary, canon


def _boundary(seq: int, kind: str, key: str, request: object, response: object) -> Boundary:
    b = Boundary(seq, kind, key, request, response)
    b.chain_hash = canon([kind, key, request, response]).hex()
    return b


def _cassette() -> Cassette:
    return Cassette(
        boundaries=[
            _boundary(0, "uuid", "uuid4", None, "id-1"),
            _boundary(1, "http", "/v1/chat", {"body": "ask A"}, {"body": "answer A"}),
            _boundary(2, "http", "/v1/chat", {"body": "ask B"}, {"body": "answer B"}),
        ],
        fingerprint="fp",
    )


def test_identical_runs_do_not_diverge() -> None:
    a = _cassette()
    b = copy.deepcopy(a)
    result = first_divergence(a, b)
    assert not result.diverged
    assert result.index is None


def test_same_input_different_output_is_classified() -> None:
    a = _cassette()
    b = copy.deepcopy(a)
    # boundary #2: identical request, different response -> the decision diverged there.
    b.boundaries[2].response = {"body": "DIFFERENT answer"}

    result = first_divergence(a, b)
    assert result.diverged
    assert result.index == 2
    assert "same input" in result.reason


def test_different_input_is_classified_as_upstream() -> None:
    a = _cassette()
    b = copy.deepcopy(a)
    b.boundaries[2].request = {"body": "a DIFFERENT ask"}

    result = first_divergence(a, b)
    assert result.diverged
    assert result.index == 2
    assert "different input" in result.reason


def test_length_divergence_reports_extra_step() -> None:
    a = _cassette()
    b = copy.deepcopy(a)
    b.boundaries.append(_boundary(3, "http", "/v1/chat", {"body": "ask C"}, {"body": "answer C"}))

    result = first_divergence(a, b)
    assert result.diverged
    assert result.index == 3
    assert "extra step" in result.reason
