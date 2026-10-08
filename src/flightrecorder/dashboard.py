"""Self-contained read-only HTML investigation desk, safe for offline sharing."""

from __future__ import annotations

import json
from dataclasses import asdict
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from .bisect import first_divergence
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
) -> None:
    for cassette in runs.values():
        validate(cassette)
    labels = list(runs)
    comparisons = []
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            result = first_divergence(runs[left], runs[right])
            try:
                aligned = diagnose(runs[left], runs[right], model_path=alignment_model)
            except ValueError as exc:
                aligned = {"alignment": [], "unavailable": str(exc)}
            comparisons.append(
                {
                    "a": left,
                    "b": right,
                    "index": result.index,
                    "diverged": result.diverged,
                    "reason": result.reason,
                    "diagnosis": aligned,
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
