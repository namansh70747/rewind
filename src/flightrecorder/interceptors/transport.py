"""HTTP capture at the httpx transport layer (ADR-0007).

Every LLM/tool HTTP call is routed through the :class:`~flightrecorder.boundary.Session`.
In replay mode ``inner`` is never touched — that is the network kill-switch: no outbound
request can escape unless it was served from the recording.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from ..boundary import Session


class RecordingTransport(httpx.BaseTransport):
    """An httpx transport that records/serves each request through a ``Session``."""

    def __init__(self, session: Session, inner: httpx.BaseTransport | None = None) -> None:
        self._session = session
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        req_repr: dict[str, Any] = {
            "method": request.method,
            "url": str(request.url),
            "body": json.loads(body) if body else None,
        }

        def produce() -> dict[str, Any]:
            if self._inner is None:  # pragma: no cover - defensive; replay never calls this
                raise RuntimeError("record mode requires an inner transport")
            resp = self._inner.handle_request(request)
            resp.read()
            return {"status": resp.status_code, "body": json.loads(resp.content)}

        rec = self._session.mediate("http", request.url.path, req_repr, produce)
        return httpx.Response(status_code=rec["status"], json=rec["body"], request=request)
