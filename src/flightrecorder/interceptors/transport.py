"""HTTP capture at the httpx transport layer (ADR-0007).

Every LLM/tool HTTP call is routed through the :class:`~flightrecorder.boundary.Session`.
In replay mode ``inner`` is never touched — that is the network kill-switch: no outbound
request can escape unless it was served from the recording.

**Phase-0 body handling.** A body is captured as ``{"json": <obj>}`` when it parses as
JSON, otherwise as ``{"text": <decoded>}``, otherwise ``None`` (empty, e.g. a 204). This
means a non-JSON body (an error HTML page, an empty response) is recorded rather than
crashing ``record`` with a ``JSONDecodeError``. Binary bodies are decoded lossily for now;
byte-exact binary + streaming (SSE) capture arrives with the streaming work.
**Request headers are intentionally not captured** — this keeps ``Authorization`` out of
recordings, at the cost of not replaying header-dependent behavior (acceptable for Phase 0).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from ..redaction import redact

if TYPE_CHECKING:
    from ..boundary import Session


def _encode_body(raw: bytes | None) -> dict[str, Any] | None:
    """Represent a request/response body as JSON if possible, else text, else nothing."""
    if not raw:
        return None
    try:
        return {"json": json.loads(raw)}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"text": raw.decode("utf-8", errors="replace")}


class RecordingTransport(httpx.BaseTransport):
    """An httpx transport that records/serves each request through a ``Session``."""

    def __init__(self, session: Session, inner: httpx.BaseTransport | None = None) -> None:
        self._session = session
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Redact at capture: secrets in the URL/body never reach the boundary log or store.
        # Redaction is deterministic, so replay redacts the live request the same way and
        # still matches the recording.
        req_repr: dict[str, Any] = redact(
            {
                "method": request.method,
                "url": str(request.url),
                "body": _encode_body(request.content),
            }
        )

        def produce() -> dict[str, Any]:
            if self._inner is None:  # pragma: no cover - defensive; replay never calls this
                raise RuntimeError("record mode requires an inner transport")
            resp = self._inner.handle_request(request)
            resp.read()
            recorded: dict[str, Any] = redact(
                {"status": resp.status_code, "body": _encode_body(resp.content)}
            )
            return recorded

        rec = self._session.mediate("http", request.url.path, req_repr, produce)
        return _rebuild_response(rec, request)


def _rebuild_response(rec: dict[str, Any], request: httpx.Request) -> httpx.Response:
    status = int(rec["status"])
    body = rec.get("body")
    if body is None:
        return httpx.Response(status_code=status, request=request)
    if "json" in body:
        return httpx.Response(status_code=status, json=body["json"], request=request)
    return httpx.Response(status_code=status, text=body["text"], request=request)
