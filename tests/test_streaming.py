"""Streaming (SSE) capture & replay for unmodified agents.

A streamed response (Server-Sent Events) arrives as multiple chunks. We record the chunk
sequence and hand the same frames back on replay, so a `client.stream(...)` agent that
parses SSE reproduces bit-exact — sync and async. No flightrecorder imports in the agent.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx

from flightrecorder import RunStore, capture, verify_run

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import pytest

_URL = "https://api.openai.com/v1/chat/completions"
_FRAMES = [
    b'data: {"choices": [{"delta": {"content": "Hel"}}]}\n\n',
    b'data: {"choices": [{"delta": {"content": "lo"}}]}\n\n',
    b"data: [DONE]\n\n",
]


def _stub_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=iter(list(_FRAMES)),
            request=request,
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)


def _stub_sse_async(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        async def _frames() -> AsyncIterator[bytes]:
            for frame in _FRAMES:
                yield frame

        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_frames(), request=request
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)


def _sse_agent() -> list[str]:
    lines: list[str] = []
    with (
        httpx.Client() as client,
        client.stream("POST", _URL, json={"model": "m", "stream": True, "messages": []}) as resp,
    ):
        lines.extend(line for line in resp.iter_lines() if line.strip())
    return lines


async def _async_sse_agent() -> list[str]:
    lines: list[str] = []
    async with (
        httpx.AsyncClient() as client,
        client.stream("POST", _URL, json={"model": "m", "stream": True, "messages": []}) as resp,
    ):
        lines = [line async for line in resp.aiter_lines() if line.strip()]
    return lines


def test_sync_sse_capture_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_sse(monkeypatch)
    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="openai", model="m") as cap:
        live = _sse_agent()

    assert cap.cassette is not None
    http = cap.cassette.boundaries[-1].response
    assert "chunks" in http and len(http["chunks"]) == len(_FRAMES)  # SSE frames preserved
    assert http.get("content_type") == "text/event-stream"
    assert len(live) == len(_FRAMES) and "Hel" in live[0]  # agent parsed the streamed frames

    result = verify_run(cap.cassette, _sse_agent, n=20)
    assert result.passed, result.detail
    store.close()


def test_async_sse_capture_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_sse_async(monkeypatch)
    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="openai", model="m") as cap:
        asyncio.run(_async_sse_agent())

    assert cap.cassette is not None
    http = cap.cassette.boundaries[-1].response
    assert "chunks" in http and len(http["chunks"]) == len(_FRAMES)

    result = verify_run(cap.cassette, lambda: asyncio.run(_async_sse_agent()), n=20)
    assert result.passed, result.detail
    store.close()
