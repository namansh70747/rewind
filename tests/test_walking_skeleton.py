"""Offline proof for the Phase-0 walking skeleton — runs in CI with no API key.

A mock transport stands in for a (nondeterministic) LLM provider. We record the bundled
example agent, persist it to a temporary SQLite store, then show that:

1. it round-trips through storage and replays bit-exact 50x;
2. the content-addressed blob store deduplicates identical payloads;
3. tampering with a stored recording is caught and localized;
4. the `fr` CLI (`show`, `verify`, `runs`) works end-to-end against the store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from typer.testing import CliRunner

from flightrecorder import RunStore, record, verify
from flightrecorder.cli import app
from flightrecorder.example_agent import Run, make_example_run
from flightrecorder.providers import OPENAI

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

RESPONSES = ["The number is 7.", "OK", "Confirmed doubled=14."]


def _mock_transport() -> httpx.MockTransport:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        content = RESPONSES[i] if i < len(RESPONSES) else f"extra-{i}"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def _record_example(tmp_path: Path) -> tuple[RunStore, str, Run]:
    run = make_example_run(OPENAI, api_key="test-key")
    cassette = record(run, _mock_transport(), provider="openai", model="gpt-4o-mini")
    store = RunStore(tmp_path / "runs.db")
    run_id = store.save(cassette)
    return store, run_id, run


def test_record_roundtrip_and_verify_bit_exact(tmp_path: Path) -> None:
    store, run_id, run = _record_example(tmp_path)
    loaded = store.load(run_id)

    assert [b.kind for b in loaded.boundaries] == ["uuid", "clock", "rng", "http", "http", "http"]

    result = verify(loaded, run, n=50)
    assert result.passed, result.detail
    assert result.unique_outputs == 1
    assert result.unique_fingerprints == 1
    store.close()


def test_content_addressed_dedup(tmp_path: Path) -> None:
    store, _, _ = _record_example(tmp_path)
    before = store.blob_count()
    # Saving the identical recording again must not duplicate any blob.
    store.save(store.load(store.list_runs()[0].id))
    assert store.blob_count() == before
    store.close()


def test_tamper_is_caught_and_localized(tmp_path: Path) -> None:
    store, run_id, run = _record_example(tmp_path)
    loaded = store.load(run_id)
    loaded.boundaries[3].response["body"]["json"]["choices"][0]["message"]["content"] = "TAMPERED"

    result = verify(loaded, run, n=1)
    assert not result.passed
    assert "boundary #3" in result.detail
    store.close()


def test_cli_show_verify_runs(tmp_path: Path) -> None:
    store, run_id, _ = _record_example(tmp_path)
    store.close()
    db = str(tmp_path / "runs.db")
    runner = CliRunner()

    r_show = runner.invoke(app, ["show", run_id, "--db", db])
    assert r_show.exit_code == 0, r_show.output
    assert "fingerprint" in r_show.output

    r_verify = runner.invoke(app, ["verify", run_id, "--n", "10", "--db", db])
    assert r_verify.exit_code == 0, r_verify.output
    assert "PASS" in r_verify.output

    r_runs = runner.invoke(app, ["runs", "--db", db])
    assert r_runs.exit_code == 0, r_runs.output


def test_cli_record_wiring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Lock the `fr record` entrypoint (console script + wiring) without a key or network:
    # stub the CLI's live transport with the mock and provide a dummy key.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda *a, **k: _mock_transport())
    db = str(tmp_path / "runs.db")

    result = CliRunner().invoke(app, ["record", "--provider", "openai", "--db", db])
    assert result.exit_code == 0, result.output

    store = RunStore(db)
    runs = store.list_runs()
    store.close()
    assert len(runs) == 1
    assert runs[0].provider == "openai"
