"""Controlled one-boundary fork experiments with explicit score and provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .boundary import canon
from .fork import fork_run
from .replay import verify

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from .boundary import Cassette
    from .fork import Mock
    from .replay import Run
    from .store import RunStore


def evaluate_forks(
    parent: Cassette,
    run: Run,
    *,
    at: int,
    values: Iterable[Any],
    make_mocks: Callable[[], Mapping[tuple[str, str], Mock]],
    score: Callable[[str], float],
    repeats: int = 3,
    store: RunStore | None = None,
) -> dict[str, Any]:
    """Change exactly one intervention; recreate fixtures for every trial.

    Score is application-defined and is not a causal or model-quality claim.
    Every saved child must itself verify before its score is reported.
    """
    rows = []
    for value in values:
        child = fork_run(parent, run, at=at, value=value, mocks=make_mocks())
        result = verify(child, run, repeats)
        if not result.passed:
            raise ValueError(f"experiment child is not replayable: {result.detail}")
        assert child.boundaries[:at] == parent.boundaries[:at]
        target = parent.boundaries[at]
        changed = child.boundaries[at]
        assert canon([target.kind, target.key, target.request]) == canon(
            [changed.kind, changed.key, changed.request]
        )
        rows.append(
            {
                "intervention": value,
                "fingerprint": child.fingerprint,
                "run_id": store.save(child) if store is not None else None,
                "score": float(score(child.final_output)),
                "replays": result.runs,
                "counterfactual": True,
                "interpretation": "controlled best-effort exploration",
            }
        )
    return {"parent_fingerprint": parent.fingerprint, "fork_at": at, "trials": rows}
