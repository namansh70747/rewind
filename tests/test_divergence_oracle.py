"""Week 5 divergence oracle — BLAKE3 chain, localized tamper, strict entropy.

Proves three exit criteria from the roadmap:

1. The boundary hash-chain is BLAKE3 and an edited response changes the link.
2. Any injected divergence is caught and named at the exact boundary.
3. A discarded ``time`` / ``random`` / ``uuid`` / ``os.urandom`` read cannot pass
   ``--strict`` (it may still pass non-strict, which is the silent-divergence case).
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import blake3
import httpx
import pytest
from typer.testing import CliRunner

from flightrecorder import RunStore, capture, record, verify, verify_run
from flightrecorder.boundary import GENESIS, Session, canon, chain_link
from flightrecorder.cli import app
from flightrecorder.example_agent import Run, make_example_run
from flightrecorder.providers import OPENAI

if TYPE_CHECKING:
    from collections.abc import Callable

RESPONSES = ["The number is 7.", "OK", "Confirmed doubled=14."]
_DEMO = Path(__file__).resolve().parents[1] / "demos" / "week2_mam"


def _mock_transport() -> httpx.MockTransport:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = state["n"]
        state["n"] += 1
        content = RESPONSES[i] if i < len(RESPONSES) else f"extra-{i}"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.MockTransport(handler)


def _pure(leak: Callable[[], object]) -> Run:
    def run(session: Session, transport: httpx.BaseTransport | None) -> str:
        _ = (session, transport)
        leak()
        return "ok"

    return run


def _leak_time() -> None:
    time.time()


def _leak_random() -> None:
    random.random()


def _leak_uuid() -> None:
    uuid.uuid4()


def _leak_urandom() -> None:
    os.urandom(8)


def _record_example(tmp_path: Path) -> tuple[RunStore, str]:
    run = make_example_run(OPENAI, api_key="test-key")
    cassette = record(run, _mock_transport(), provider="openai", model="gpt-4o-mini")
    store = RunStore(tmp_path / "runs.db")
    run_id = store.save(cassette)
    return store, run_id


def test_chain_link_is_blake3_of_the_concatenation() -> None:
    req = b'{"a":1}'
    resp = b'{"b":2}'
    prev = bytes.fromhex(GENESIS)
    expect = blake3.blake3(prev + req + resp).hexdigest()
    assert chain_link(GENESIS, req, resp) == expect
    assert len(expect) == 64

    stale = hashlib.blake2b(digest_size=32)
    stale.update(prev)
    stale.update(req)
    stale.update(resp)
    assert expect != stale.hexdigest()


def test_response_edit_changes_this_link_and_the_next() -> None:
    req = canon(["http", "/v1", {"n": 1}])
    first = chain_link(GENESIS, req, canon("clear skies"))
    edited = chain_link(GENESIS, req, canon("heavy rain"))
    assert first != edited
    assert chain_link(first, b"next", b"ok") != chain_link(edited, b"next", b"ok")


def test_chain_link_is_deterministic() -> None:
    payload = canon({"k": "v", "n": 1})
    assert chain_link(GENESIS, payload, payload) == chain_link(GENESIS, payload, payload)


@pytest.mark.parametrize(
    ("source", "leak"),
    [
        ("time.time", _leak_time),
        ("random.random", _leak_random),
        ("uuid.uuid4", _leak_uuid),
        ("os.urandom", _leak_urandom),
    ],
)
def test_discarded_entropy_is_silent_until_strict(source: str, leak: Callable[[], None]) -> None:
    run = _pure(leak)
    cassette = record(run, _mock_transport())
    assert cassette.boundaries == []
    assert cassette.fingerprint == GENESIS

    plain = verify(cassette, run, n=2)
    assert plain.passed, plain.detail
    assert plain.verdict == "replay verified ✓"

    strict = verify(cassette, run, n=1, strict=True)
    assert not strict.passed
    assert strict.verdict == "replay verified ✗"
    assert source in strict.detail
    assert "boundary #0" in strict.detail
    assert "strict mode" in strict.detail


def test_clock_baked_into_the_request_diverges_without_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(session: Session, transport: httpx.BaseTransport | None) -> str:
        _ = transport
        stamp = time.time()
        session.mediate("probe", "clock-in-request", {"t": stamp}, lambda: "ok")
        return "ok"

    cassette = record(run, _mock_transport())
    monkeypatch.setattr(time, "time", lambda: 0.0)
    result = verify(cassette, run, n=1)
    assert not result.passed
    assert result.verdict == "replay verified ✗"
    assert "boundary #0" in result.detail
    assert "input diverged" in result.detail


def test_session_shims_pass_strict() -> None:
    run = make_example_run(OPENAI, api_key="test-key")
    cassette = record(run, _mock_transport(), provider="openai", model="gpt-4o-mini")
    result = verify(cassette, run, n=5, strict=True)
    assert result.passed, result.detail
    assert result.verdict == "replay verified ✓"
    assert "PASS" in str(result)


def test_tamper_is_localized_to_the_edited_boundary(tmp_path: Path) -> None:
    store, run_id = _record_example(tmp_path)
    loaded = store.load(run_id)
    loaded.boundaries[3].response["body"]["json"]["choices"][0]["message"]["content"] = "TAMPERED"
    run = make_example_run(OPENAI, api_key="test-key")
    result = verify(loaded, run, n=1)
    store.close()
    assert not result.passed
    assert "boundary #3" in result.detail
    assert "hash-chain mismatch" in result.detail
    assert result.verdict == "replay verified ✗"


def test_uncaptured_clock_between_http_calls_names_that_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        _ = self
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle)

    def agent() -> None:
        with httpx.Client() as client:
            client.get("https://example.test/one")
            time.time()
            client.get("https://example.test/two")

    with capture() as cap:
        agent()
    assert cap.cassette is not None
    assert [b.kind for b in cap.cassette.boundaries] == ["http", "http"]

    plain = verify_run(cap.cassette, agent, n=1)
    assert plain.passed, plain.detail
    strict = verify_run(cap.cassette, agent, n=1, strict=True)
    assert not strict.passed
    assert "time.time" in strict.detail
    assert "boundary #1" in strict.detail


def test_blob_addresses_stay_blake2b(tmp_path: Path) -> None:
    store, run_id = _record_example(tmp_path)
    loaded = store.load(run_id)
    raw = canon(loaded.boundaries[0].request)
    expect = hashlib.blake2b(raw, digest_size=32).hexdigest()
    row = store.conn.execute("SELECT hash FROM blob WHERE hash = ?", (expect,)).fetchone()
    store.close()
    assert row is not None
    assert blake3.blake3(raw).hexdigest() != expect


def test_cli_verify_help_documents_strict() -> None:
    result = CliRunner().invoke(app, ["verify", "--help"])
    assert result.exit_code == 0, result.output
    assert "--strict" in result.output


def test_cli_record_verify_strict_and_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda *a, **k: _mock_transport())
    db = str(tmp_path / "runs.db")
    runner = CliRunner()

    recorded = runner.invoke(app, ["record", "--provider", "openai", "--db", db])
    assert recorded.exit_code == 0, recorded.output

    store = RunStore(db)
    run_id = store.list_runs()[0].id
    store.close()

    verified = runner.invoke(app, ["verify", run_id, "--n", "4", "--strict", "--db", db])
    assert verified.exit_code == 0, verified.output
    assert "replay verified ✓" in verified.output
    assert "PASS" in verified.output
    assert "strict" in verified.output

    store = RunStore(db)
    tampered = store.load(run_id)
    tampered.boundaries[4].response["body"]["json"]["choices"][0]["message"]["content"] = "NOPE"
    bad_id = store.save(tampered)
    store.close()

    failed = runner.invoke(app, ["verify", bad_id, "--n", "1", "--db", db])
    assert failed.exit_code == 1, failed.output
    assert "replay verified ✗" in failed.output
    assert "boundary #4" in failed.output


def test_fr_executable_e2e_verify_and_tamper(tmp_path: Path) -> None:
    """Real ``fr`` process: record via the library, verify and tamper via the console script."""
    fr = shutil.which("fr")
    assert fr is not None, "fr console script is not on PATH"

    store, run_id = _record_example(tmp_path)
    db = str(tmp_path / "runs.db")
    loaded = store.load(run_id)
    loaded.boundaries[5].response["body"]["json"]["choices"][0]["message"]["content"] = "EDITED"
    bad_id = store.save(loaded)
    store.close()

    good = subprocess.run(
        [fr, "verify", run_id, "--n", "3", "--strict", "--db", db],
        check=False,
        capture_output=True,
        text=True,
    )
    assert good.returncode == 0, good.stdout + good.stderr
    assert "replay verified ✓" in good.stdout

    shown = subprocess.run(
        [fr, "show", run_id, "--db", db],
        check=False,
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert "fingerprint" in shown.stdout

    bad = subprocess.run(
        [fr, "verify", bad_id, "--n", "1", "--db", db],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    combined = bad.stdout + bad.stderr
    assert "replay verified ✗" in combined
    assert "boundary #5" in combined


def test_ui_proof_card_names_replay_verified() -> None:
    html = (_DEMO / "static" / "index.html").read_text(encoding="utf-8")
    js = (_DEMO / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="proof-verdict"' in html
    assert "replay verified ✓" in js
    assert "replay verified ✗" in js
