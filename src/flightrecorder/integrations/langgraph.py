"""LangGraph state-stream adapter; capture graph boundaries and explicit snapshots."""

from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING, Any

from ..capture import _patched
from ..redaction import redact

if TYPE_CHECKING:
    from ..boundary import Session


def run_graph(
    graph: Any, inputs: dict[str, Any], session: Session, config: dict[str, Any] | None = None
) -> str:
    """Run a compiled graph with fresh/checkpoint-isolated state for each replay.

    Existing checkpointer thread state is NOT restored. Use a fresh graph/thread;
    deterministic snapshot requests expose state drift instead of masking it.
    """
    latest: Any = None
    with _patched(session):
        for index, state in enumerate(graph.stream(inputs, config=config, stream_mode="values")):
            safe = redact(state)
            latest = session.mediate(
                "state", f"langgraph/{index}", safe, partial(lambda value: value, safe)
            )
    return json.dumps(latest, sort_keys=True)


async def arun_graph(
    graph: Any, inputs: dict[str, Any], session: Session, config: dict[str, Any] | None = None
) -> str:
    latest: Any = None
    index = 0
    with _patched(session):
        async for state in graph.astream(inputs, config=config, stream_mode="values"):
            safe = redact(state)
            latest = session.mediate(
                "state", f"langgraph/{index}", safe, partial(lambda value: value, safe)
            )
            index += 1
    return json.dumps(latest, sort_keys=True)
