"""Logical LangGraph thread/checkpoint evidence through the native callback API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import BaseCallbackHandler

from ..boundary import Divergence
from ..offline import NetworkBlocked
from ..state import encode_state

if TYPE_CHECKING:
    from uuid import UUID

    from ..boundary import Session


class RewindCallback(BaseCallbackHandler):
    """Capture logical chain completions, excluding random framework run IDs.

    run_inline keeps callbacks in the graph's event loop rather than executor
    threads. Thread identity and declared outputs are portable state evidence.
    """

    run_inline = True
    raise_error = True

    def __init__(self, session: Session, thread_id: str) -> None:
        self.session = session
        self.thread_id = thread_id
        self.names: dict[UUID, str] = {}
        self.sequence = 0

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.names[run_id] = str(kwargs.get("name") or (serialized or {}).get("name", "chain"))

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._emit(run_id, "completed", outputs)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        if isinstance(error, (Divergence, NetworkBlocked)):
            self.names.pop(run_id, None)
            return
        self._emit(run_id, "error", {"type": type(error).__name__, "message": str(error)})

    def _emit(self, run_id: UUID, status: str, output: Any) -> None:
        evidence = encode_state(
            {
                "thread_id": self.thread_id,
                "name": self.names.pop(run_id, "chain"),
                "status": status,
                "outputs": output,
            }
        )
        self.session.mediate("callback", f"langgraph/{self.sequence}", evidence, lambda: evidence)
        self.sequence += 1
