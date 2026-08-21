"""HTTP capture at the httpx transport layer (ADR-0007).

Every LLM/tool HTTP call is routed through the :class:`~flightrecorder.boundary.Session`.
In replay mode ``inner`` is never touched — that is the network kill-switch: no outbound
request can escape unless it was served from the recording.

**Body handling.** A response is captured as its decoded chunk sequence. The assembled body
is stored as ``{"json": <obj>}`` when it parses, else ``{"text": <decoded>}``, else ``None``
(empty, e.g. a 204) — so a non-JSON body (error HTML, empty response) is recorded rather
than crashing ``record``. When a response arrives in **more than one chunk** (streaming /
SSE), the individual chunks and the ``content-type`` are also stored so replay can hand the
agent back the same streamed frames it saw live. Binary bodies are decoded lossily for now.

**Request headers are intentionally not captured** — this keeps ``Authorization`` out of
recordings, at the cost of not replaying header-dependent behavior (acceptable for Phase 0).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from ..redaction import redact, redact_text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ..boundary import Session


def _encode_body(raw: bytes | None) -> dict[str, Any] | None:
    """Represent an assembled body as JSON if possible, else text, else nothing."""
    if not raw:
        return None
    try:
        return {"json": json.loads(raw)}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"text": raw.decode("utf-8", errors="replace")}


def _encode_response(chunks: list[bytes], content_type: str | None) -> dict[str, Any]:
    """Build the recorded response value from its decoded chunk sequence.

    Secrets are scrubbed on the *assembled* text first. Per-chunk redaction is used for
    streamed replay only when it matches the assembled result — if a secret spans a chunk
    boundary, we collapse to a single redacted frame so nothing leaks via ``chunks``.
    """
    texts = [chunk.decode("utf-8", errors="replace") for chunk in chunks]
    safe_full = redact_text("".join(texts))
    rec: dict[str, Any] = {"body": _encode_body(safe_full.encode("utf-8"))}
    if len(chunks) > 1:  # streamed — preserve frame boundaries when safe
        safe_chunks = [redact_text(text) for text in texts]
        if "".join(safe_chunks) != safe_full:
            # Spanning secret: per-chunk redaction would miss it and leak on replay.
            safe_chunks = [safe_full]
        rec["chunks"] = safe_chunks
        if content_type:
            rec["content_type"] = content_type
    return rec


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
            chunks = list(resp.iter_bytes())
            recorded: dict[str, Any] = redact(
                {
                    "status": resp.status_code,
                    **_encode_response(chunks, resp.headers.get("content-type")),
                }
            )
            return recorded

        rec = self._session.mediate("http", request.url.path, req_repr, produce)
        return _rebuild_response(rec, request)


class AsyncRecordingTransport(httpx.AsyncBaseTransport):
    """Async twin of :class:`RecordingTransport` for ``httpx.AsyncClient``."""

    def __init__(self, session: Session, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._session = session
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        req_repr: dict[str, Any] = redact(
            {
                "method": request.method,
                "url": str(request.url),
                "body": _encode_body(request.content),
            }
        )

        async def produce() -> dict[str, Any]:
            if self._inner is None:  # pragma: no cover - defensive; replay never calls this
                raise RuntimeError("record mode requires an inner transport")
            resp = await self._inner.handle_async_request(request)
            chunks = [chunk async for chunk in resp.aiter_bytes()]
            recorded: dict[str, Any] = redact(
                {
                    "status": resp.status_code,
                    **_encode_response(chunks, resp.headers.get("content-type")),
                }
            )
            return recorded

        rec = await self._session.mediate_async("http", request.url.path, req_repr, produce)
        return _rebuild_response(rec, request, is_async=True)


def _rebuild_response(
    rec: dict[str, Any], request: httpx.Request, *, is_async: bool = False
) -> httpx.Response:
    status = int(rec["status"])
    if "chunks" in rec:  # streamed — hand back the same frames as a live stream
        chunk_bytes = [chunk.encode("utf-8") for chunk in rec["chunks"]]
        headers = {"content-type": rec["content_type"]} if rec.get("content_type") else None
        content: Any
        if is_async:

            async def _agen() -> AsyncIterator[bytes]:
                for chunk in chunk_bytes:
                    yield chunk

            content = _agen()
        else:
            content = iter(chunk_bytes)
        return httpx.Response(status_code=status, headers=headers, content=content, request=request)
    body = rec.get("body")
    if body is None:
        return httpx.Response(status_code=status, request=request)
    if "json" in body:
        return httpx.Response(status_code=status, json=body["json"], request=request)
    return httpx.Response(status_code=status, text=body["text"], request=request)
