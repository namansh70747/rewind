"""Global capture of UNMODIFIED *async* agents (httpx.AsyncClient).

Mirrors the sync suite — happy path, diverge-loud, proxy/mount — and adds the v1
concurrency policy: concurrent boundaries (`asyncio.gather` of HTTP calls) must fail loud,
not silently corrupt the hash-chain. Agents are driven/replayed with `asyncio.run(...)`, so
no pytest-asyncio is needed, and they use only `httpx` (no flightrecorder imports).
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import httpx
import pytest

from flightrecorder import Divergence, RunStore, capture, verify_run
from flightrecorder.offline import NetworkBlocked, offline_guard

if TYPE_CHECKING:
    from pathlib import Path

RESPONSES = ["seven", "ok", "done"]
_URL = "https://api.openai.com/v1/chat/completions"


async def _async_agent() -> str:
    out = []
    async with httpx.AsyncClient() as client:
        for prompt in ("first", "second"):
            resp = await client.post(
                _URL, json={"model": "m", "messages": [{"role": "user", "content": prompt}]}
            )
            out.append(resp.json()["choices"][0]["message"]["content"])
    return " ".join(out)


def _stub_async_provider(monkeypatch: pytest.MonkeyPatch, *, yield_control: bool = False) -> None:
    state = {"n": 0}

    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        if yield_control:
            await asyncio.sleep(0)  # force gathered calls to actually interleave
        i = state["n"]
        state["n"] += 1
        content = RESPONSES[i] if i < len(RESPONSES) else f"x{i}"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}, request=request
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)


def test_capture_and_replay_unmodified_async_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_async_provider(monkeypatch)
    store = RunStore(tmp_path / "runs.db")

    with capture(store, provider="openai", model="m") as cap:
        asyncio.run(_async_agent())

    assert cap.cassette is not None
    assert [b.kind for b in cap.cassette.boundaries] == ["http", "http"]

    result = verify_run(cap.cassette, lambda: asyncio.run(_async_agent()), n=20)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1
    store.close()


def test_async_replay_diverges_loudly_if_agent_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_async_provider(monkeypatch)
    with capture(provider="openai", model="m") as cap:
        asyncio.run(_async_agent())
    assert cap.cassette is not None

    async def _changed() -> str:
        async with httpx.AsyncClient() as client:
            for prompt in ("first", "second", "third"):  # one extra call the recording never saw
                await client.post(
                    _URL, json={"model": "m", "messages": [{"role": "user", "content": prompt}]}
                )
        return "changed"

    result = verify_run(cap.cassette, lambda: asyncio.run(_changed()), n=1)
    assert not result.passed


def test_proxy_mount_async_transport_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A proxied AsyncClient routes via _mounts; those must be recorded too."""
    _stub_async_provider(monkeypatch)

    async def _proxied() -> str:
        async with httpx.AsyncClient(proxy="http://proxy.invalid:8080") as client:
            await client.post(
                _URL, json={"model": "m", "messages": [{"role": "user", "content": "first"}]}
            )
        return "ok"

    with capture(provider="openai", model="m") as cap:
        asyncio.run(_proxied())
    assert cap.cassette is not None
    assert [b.kind for b in cap.cassette.boundaries] == ["http"]  # captured via the mount

    result = verify_run(cap.cassette, lambda: asyncio.run(_proxied()), n=5)
    assert result.passed, result.detail


def test_concurrent_async_boundaries_fail_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """v1 is serialized: asyncio.gather of HTTP calls is detected and raised, not corrupted."""
    _stub_async_provider(monkeypatch, yield_control=True)

    async def _gather_agent() -> None:
        async with httpx.AsyncClient() as client:
            await asyncio.gather(
                client.post(
                    _URL, json={"model": "m", "messages": [{"role": "user", "content": "a"}]}
                ),
                client.post(
                    _URL, json={"model": "m", "messages": [{"role": "user", "content": "b"}]}
                ),
            )

    with pytest.raises(Divergence), capture(provider="openai", model="m"):
        asyncio.run(_gather_agent())


def test_async_thread_wakeup_preserves_offline_guard() -> None:
    async def wakeup() -> int:
        return await asyncio.to_thread(lambda: 42)

    with offline_guard() as audit:
        assert asyncio.run(wakeup()) == 42
        assert not audit.blocked_operations
        with socket.socket() as sock, pytest.raises(NetworkBlocked):
            sock.connect(("127.0.0.1", 9))
        assert audit.blocked_operations == ["connect"]


def test_local_socketpair_wakeup_does_not_disable_offline_guard() -> None:
    with offline_guard() as audit:
        left, right = socket.socketpair()
        try:
            left.send(b"x")
            assert right.recv(1) == b"x"
            with pytest.raises(NetworkBlocked):
                socket.socket().connect(("127.0.0.1", 9))
        finally:
            left.close()
            right.close()
    assert audit.blocked_operations == ["connect"]
