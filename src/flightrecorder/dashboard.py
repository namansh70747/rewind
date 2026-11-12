"""Self-contained read-only HTML investigation desk, safe for offline sharing."""

from __future__ import annotations

import json
from dataclasses import asdict
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from .diagnosis import diagnose
from .integrity import validate

if TYPE_CHECKING:
    from pathlib import Path

    from .boundary import Cassette


def render_dashboard(
    runs: dict[str, Cassette],
    output: Path,
    verification: dict[str, Any] | None = None,
    *,
    alignment_model: Path | None = None,
    alignment_vectors: tuple[list[list[float]], list[list[float]]] | None = None,
) -> None:
    for cassette in runs.values():
        validate(cassette)
    labels = list(runs)
    comparisons = []
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            try:
                aligned = diagnose(
                    runs[left],
                    runs[right],
                    model_path=alignment_model,
                    vectors=alignment_vectors if len(labels) == 2 else None,
                )
                reverse_vectors = (
                    (alignment_vectors[1], alignment_vectors[0])
                    if alignment_vectors is not None and len(labels) == 2
                    else None
                )
                reverse = diagnose(
                    runs[right], runs[left], model_path=alignment_model, vectors=reverse_vectors
                )
            except ValueError as exc:
                aligned = reverse = {"alignment": [], "unavailable": str(exc)}
            first = aligned.get("primary_difference")
            comparisons.append(
                {
                    "a": left,
                    "b": right,
                    "index": (first["a"] if first["a"] is not None else first["b"])
                    if first
                    else None,
                    "diverged": first is not None,
                    "reason": first["summary"]
                    if first
                    else aligned.get("unavailable", "identical"),
                    "diagnosis": aligned,
                    "reverse_diagnosis": reverse,
                }
            )
    data = {
        "runs": {name: asdict(c) for name, c in runs.items()},
        "comparisons": comparisons,
        "verification": verification or {},
    }
    # Prevent script-tag breakout even for adversarial prompts. UI uses textContent.
    payload = (
        json.dumps(data, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = files("flightrecorder").joinpath("web.html").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__REWIND_DATA__", payload), encoding="utf-8")
