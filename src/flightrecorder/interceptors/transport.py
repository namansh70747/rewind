"""HTTP capture at the httpx transport layer (ADR-0007).

Every LLM/tool HTTP call is routed through the :class:`~flightrecorder.boundary.Session`.
In replay mode ``inner`` is never touched — that is the network kill-switch: no outbound
request can escape unless it was served from the recording.

**Body handling.** A response is captured as its decoded chunk sequence. The assembled body
is stored as ``{"json": <obj>}`` when it parses, else ``{"text": <decoded>}``, else ``None``
(empty, e.g. a 204) — so a non-JSON body (error HTML, empty response) is recorded rather
than crashing ``record``. When a response arrives in **more than one chunk** (streaming /
SSE), the individual chunks and the ``content-type`` are also stored so replay can hand the
agent back the same streamed frames it saw live. Non-UTF-8 binary bodies are rejected rather than silently decoded.

**Request headers are intentionally not captured** — this keeps ``Authorization`` out of
recordings, at the cost of not replaying header-dependent behavior (a documented capture limitation).
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import json
import time
from typing import TYPE_CHECKING, Any

import httpx

from ..redaction import redact, redact_text
from ..sources import suppress_sources
from ..streaming import _TIMING_SCALE, chunk_deadlines

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from ..boundary import Session


def _encode_body(raw: bytes | None) -> dict[str, Any] | None:
    """Represent an assembled body as JSON if possible, else text, else nothing."""
    if not raw:
        return None
    try:
        return {"json": json.loads(raw)}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"text": raw.decode("utf-8")}


def _sanitize_json_text(text: str) -> str:
    """Decode escaped field names before applying structured credential redaction."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return text
    safe = redact(value)
    return json.dumps(safe, ensure_ascii=False) if safe != value else text


def _sanitize_stream_text(text: str) -> str:
    safe = _sanitize_json_text(redact_text(text))
    # SSE JSON may span several data lines. Join only the data fields for parsing;
    # preserve all original bytes when no structured redaction is required.
    result: list[str] = []
    block: list[str] = []

    def flush() -> None:
        data = [line[5:].lstrip(" ").rstrip("\r\n") for line in block if line.startswith("data:")]
        joined = "\n".join(data)
        sanitized = _sanitize_json_text(joined)
        if data and sanitized != joined:
            replaced = False
            for line in block:
                if line.startswith("data:"):
                    if not replaced:
                        result.append("data: " + sanitized + "\n")
                        replaced = True
                else:
                    result.append(line)
        else:
            result.extend(block)
        block.clear()

    for line in safe.splitlines(keepends=True):
        if not line.strip():
            flush()
            result.append(line)
        else:
            block.append(line)
    flush()
    return "".join(result)


def _encode_response(chunks: list[bytes], content_type: str | None) -> dict[str, Any]:
    """Build the recorded response value from its decoded chunk sequence.

    Secrets are scrubbed on the *assembled* text first. Per-chunk redaction is used for
    streamed replay only when it matches the assembled result — if a secret spans a chunk
    boundary, we collapse to a single redacted frame so nothing leaks via ``chunks``.
    """
    decoder = codecs.getincrementaldecoder("utf-8")()
    texts = [decoder.decode(chunk) for chunk in chunks]
    tail = decoder.decode(b"", final=True)
    if tail:
        texts.append(tail)
    safe_full = _sanitize_stream_text("".join(texts))
    rec: dict[str, Any] = {"body": _encode_body(safe_full.encode("utf-8"))}
    if content_type:
        rec["content_type"] = content_type
    if len(chunks) > 1:  # streamed — preserve frame boundaries when safe
        safe_chunks = [redact_text(text) for text in texts]
        if "".join(safe_chunks) != safe_full:
            # Spanning secret: per-chunk redaction would miss it and leak on replay.
            safe_chunks = [safe_full]
        rec["chunks"] = safe_chunks
        # Preserve safe, decoded HTTP chunk bytes, including UTF-8 codepoints split
        # across chunks. Never retain original bytes when redaction changed content.
        if safe_full == "".join(texts):
            rec["chunk_bytes_b64"] = [base64.b64encode(chunk).decode("ascii") for chunk in chunks]
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
            with suppress_sources():
                try:
                    resp = self._inner.handle_request(request)
                    started = time.perf_counter_ns()
                    chunks, offsets = [], []
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        offsets.append(time.perf_counter_ns() - started)
                except httpx.TransportError as exc:
                    return {
                        "transport_error": {
                            "type": type(exc).__name__,
                            "message": redact_text(str(exc)),
                        }
                    }
            recorded: dict[str, Any] = redact(
                {
                    "status": resp.status_code,
                    **_encode_response(chunks, resp.headers.get("content-type")),
                }
            )
            if len(chunks) > 1:
                recorded["chunk_offsets_ns"] = (
                    offsets if len(recorded.get("chunks", [])) == len(offsets) else [offsets[-1]]
                )
            return recorded

        rec = self._session.mediate("http", redact_text(request.url.path), req_repr, produce)
        return _rebuild_response(
            rec,
            request,
            timing_scale=_TIMING_SCALE.get() if self._session.mode == "replay" else 0.0,
        )

    def close(self) -> None:
        if self._inner is not None:
            self._inner.close()


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
            with suppress_sources():
                try:
                    resp = await self._inner.handle_async_request(request)
                    started = time.perf_counter_ns()
                    chunks, offsets = [], []
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        offsets.append(time.perf_counter_ns() - started)
                except httpx.TransportError as exc:
                    return {
                        "transport_error": {
                            "type": type(exc).__name__,
                            "message": redact_text(str(exc)),
                        }
                    }
            recorded: dict[str, Any] = redact(
                {
                    "status": resp.status_code,
                    **_encode_response(chunks, resp.headers.get("content-type")),
                }
            )
            if len(chunks) > 1:
                recorded["chunk_offsets_ns"] = (
                    offsets if len(recorded.get("chunks", [])) == len(offsets) else [offsets[-1]]
                )
            return recorded

        rec = await self._session.mediate_async(
            "http", redact_text(request.url.path), req_repr, produce
        )
        return _rebuild_response(
            rec,
            request,
            is_async=True,
            timing_scale=_TIMING_SCALE.get() if self._session.mode == "replay" else 0.0,
        )

    async def aclose(self) -> None:
        if self._inner is not None:
            await self._inner.aclose()


def _rebuild_response(
    rec: dict[str, Any],
    request: httpx.Request,
    *,
    is_async: bool = False,
    timing_scale: float = 0.0,
) -> httpx.Response:
    if "transport_error" in rec:
        error = rec["transport_error"]
        allowed = {
            name: getattr(httpx, name)
            for name in (
                "ConnectError",
                "ConnectTimeout",
                "ReadError",
                "ReadTimeout",
                "WriteError",
                "WriteTimeout",
                "PoolTimeout",
                "RemoteProtocolError",
                "LocalProtocolError",
                "ProxyError",
                "UnsupportedProtocol",
                "TransportError",
            )
        }
        exception = allowed.get(error["type"], httpx.TransportError)
        raise exception(error["message"], request=request)
    status = int(rec["status"])
    if "chunks" in rec:  # streamed — hand back the same frames as a live stream
        chunk_bytes = (
            [base64.b64decode(chunk, validate=True) for chunk in rec["chunk_bytes_b64"]]
            if "chunk_bytes_b64" in rec
            else [chunk.encode("utf-8") for chunk in rec["chunks"]]
        )
        headers = {"content-type": rec["content_type"]} if rec.get("content_type") else None
        deadlines = chunk_deadlines(rec.get("chunk_offsets_ns"), len(chunk_bytes), timing_scale)
        content: Any
        if is_async:

            async def _agen() -> AsyncIterator[bytes]:
                started = time.monotonic()
                for chunk, deadline in zip(chunk_bytes, deadlines, strict=True):
                    if timing_scale:
                        await asyncio.sleep(max(0.0, started + deadline - time.monotonic()))
                    yield chunk

            content = _agen()
        else:

            def _gen() -> Iterator[bytes]:
                started = time.monotonic()
                for chunk, deadline in zip(chunk_bytes, deadlines, strict=True):
                    if timing_scale:
                        time.sleep(max(0.0, started + deadline - time.monotonic()))
                    yield chunk

            content = _gen()
        return httpx.Response(status_code=status, headers=headers, content=content, request=request)
    headers = {"content-type": rec["content_type"]} if rec.get("content_type") else None
    body = rec.get("body")
    if body is None:
        return httpx.Response(status_code=status, headers=headers, request=request)
    if "json" in body:
        return httpx.Response(
            status_code=status, json=body["json"], headers=headers, request=request
        )
    return httpx.Response(status_code=status, text=body["text"], headers=headers, request=request)
