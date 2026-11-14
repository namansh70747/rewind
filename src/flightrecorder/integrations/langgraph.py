"""LangGraph state-stream adapter; capture graph boundaries and explicit snapshots."""

from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING, Any

from ..capture import _patched
from ..state import decode_state, encode_state

if TYPE_CHECKING:
    from ..boundary import Session


def run_graph(
    graph: Any,
    inputs: dict[str, Any] | None,
    session: Session,
    config: dict[str, Any] | None = None,
    *,
    callbacks: bool = False,
) -> str:
    """Run a compiled graph with fresh/checkpoint-isolated state for each replay.

    Existing checkpointer thread state is NOT restored. Use a fresh graph/thread;
    deterministic snapshot requests expose state drift instead of masking it.
    """
    config = _callback_config(session, config, callbacks)
    latest: Any = None
    with _patched(session):
        for index, state in enumerate(graph.stream(inputs, config=config, stream_mode="values")):
            safe = decode_state(encode_state(state))
            latest = session.mediate(
                "state", f"langgraph/{index}", safe, partial(lambda value: value, safe)
            )
    return json.dumps(latest, sort_keys=True)


async def arun_graph(
    graph: Any,
    inputs: dict[str, Any] | None,
    session: Session,
    config: dict[str, Any] | None = None,
    *,
    callbacks: bool = False,
) -> str:
    config = _callback_config(session, config, callbacks)
    latest: Any = None
    index = 0
    with _patched(session):
        async for state in graph.astream(inputs, config=config, stream_mode="values"):
            safe = decode_state(encode_state(state))
            latest = session.mediate(
                "state", f"langgraph/{index}", safe, partial(lambda value: value, safe)
            )
            index += 1
    return json.dumps(latest, sort_keys=True)


def _callback_config(session: Session, config: dict[str, Any] | None, enabled: bool) -> Any:
    if not enabled:
        return config
    from .langgraph_callbacks import RewindCallback

    configured = dict(config or {})
    existing = configured.get("callbacks", [])
    if not isinstance(existing, list):
        raise ValueError("callback capture requires a list of existing callbacks")
    thread = str(configured.get("configurable", {}).get("thread_id", "default"))
    configured["callbacks"] = [*existing, RewindCallback(session, thread)]
    return configured


def _checkpoint_evidence(snapshot: Any, config: dict[str, Any]) -> dict[str, Any]:
    return encode_state(
        {
            "thread_id": str(config.get("configurable", {}).get("thread_id", "default")),
            "values": snapshot.values,
            "next": list(snapshot.next),
        }
    )


def capture_checkpoint(graph: Any, config: dict[str, Any], session: Session) -> dict[str, Any]:
    """Record a native checkpointer's logical thread state, not opaque execution IDs."""
    evidence = _checkpoint_evidence(graph.get_state(config), config)
    result = session.mediate("checkpoint", "langgraph/thread", evidence, lambda: evidence)
    decoded = decode_state(result)
    assert isinstance(decoded, dict)
    return decoded


async def acapture_checkpoint(
    graph: Any, config: dict[str, Any], session: Session
) -> dict[str, Any]:
    evidence = _checkpoint_evidence(await graph.aget_state(config), config)
    result = session.mediate("checkpoint", "langgraph/thread", evidence, lambda: evidence)
    decoded = decode_state(result)
    assert isinstance(decoded, dict)
    return decoded


def restore_checkpoint(
    graph: Any, evidence: dict[str, Any], config: dict[str, Any], *, as_node: str
) -> dict[str, Any]:
    """Restore declared thread values into a fresh native checkpointer.

    The application names the completed node explicitly; no guessed scheduling
    state or opaque framework IDs are restored. Validate the resulting frontier
    before executing any continuation producers.
    """
    safe = decode_state(encode_state(evidence))
    restored = graph.update_state(config, safe["values"], as_node=as_node)
    if list(graph.get_state(restored).next) != safe["next"]:
        raise ValueError("restored checkpoint frontier differs; check as_node and graph version")
    return dict(restored)


async def arestore_checkpoint(
    graph: Any, evidence: dict[str, Any], config: dict[str, Any], *, as_node: str
) -> dict[str, Any]:
    safe = decode_state(encode_state(evidence))
    restored = await graph.aupdate_state(config, safe["values"], as_node=as_node)
    if list((await graph.aget_state(restored)).next) != safe["next"]:
        raise ValueError("restored checkpoint frontier differs; check as_node and graph version")
    return dict(restored)
