"""End-to-end acceptance and adversarial regression cases for the demo release."""

from __future__ import annotations

import copy
import json
import socket
from typing import TYPE_CHECKING

import httpx
import pytest
from typer.testing import CliRunner

from flightrecorder import Cassette, Divergence, RunStore, Session, first_divergence, verify
from flightrecorder.cli import app
from flightrecorder.dashboard import render_dashboard
from flightrecorder.demo import demo_mocks, make_demo_run, record_demo, recover_demo
from flightrecorder.fork import fork_run
from flightrecorder.inspection import similarity, state_at
from flightrecorder.integrity import validate
from flightrecorder.interceptors.transport import RecordingTransport
from flightrecorder.offline import NetworkBlocked, offline_guard
from flightrecorder.portable import export_run, import_run
from flightrecorder.redaction import redact
from flightrecorder.scripts import record_script, verify_script

if TYPE_CHECKING:
    from pathlib import Path


def test_demo_records_replays_and_changes_real_execution_path() -> None:
    failed = record_demo()
    child = recover_demo(failed)
    assert json.loads(failed.final_output)["status"] == "over_budget"
    assert json.loads(child.final_output)["status"] == "confirmed"
    assert child.metadata["parent_fingerprint"] == failed.fingerprint
    assert child.boundaries[:3] == failed.boundaries[:3]
    assert child.boundaries[4].response["within_budget"] is True
    assert first_divergence(failed, child).index == 3
    assert verify(failed, make_demo_run(), 50).passed
    assert verify(child, make_demo_run(), 50).passed
    validate(child)


def test_fork_blocks_unspecified_continuation() -> None:
    with pytest.raises(Divergence, match="explicit mock"):
        fork_run(record_demo(), make_demo_run(), at=3, value={"price": 420})


def test_fork_never_calls_original_producer() -> None:
    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        def explode() -> None:
            raise AssertionError("live producer executed")

        return str(session.mediate("tool", "charge", None, explode))

    session = Session("record")
    session.mediate("tool", "charge", None, lambda: "old")
    parent = Cassette(session.boundaries, session.chain, "old")
    child = fork_run(parent, run, at=0, value="new")
    assert child.final_output == "new"


@pytest.mark.parametrize("at", [-1, 7, 500])
def test_invalid_fork_index(at: int) -> None:
    with pytest.raises(ValueError):
        fork_run(record_demo(), make_demo_run(), at=at, value=0)


def test_intervention_requires_original_input() -> None:
    def changed(session: Session, inner: httpx.BaseTransport | None) -> str:
        session.mediate("input", "wrong", None, lambda: None)
        return ""

    with pytest.raises(Divergence):
        fork_run(record_demo(), changed, at=0, value={}, mocks=demo_mocks())


def test_mutations_do_not_rewrite_recorded_evidence() -> None:
    session = Session("record")
    request = {"a": [1]}
    response = {"b": [2]}
    returned = session.mediate("tool", "x", request, lambda: response)
    cassette = Cassette(session.boundaries, session.chain)
    request["a"].append(99)
    returned["b"].append(99)
    assert cassette.boundaries[0].request == {"a": [1]}
    replay = Session("replay", cassette)
    result = replay.mediate("tool", "x", {"a": [1]}, lambda: None)
    result["b"].append(42)
    validate(cassette)
    assert cassette.boundaries[0].response == {"b": [2]}


@pytest.mark.parametrize("damage", ["sequence", "response", "fingerprint", "truncation"])
def test_integrity_rejects_corruption(damage: str) -> None:
    cassette = record_demo()
    if damage == "sequence":
        cassette.boundaries[2].seq = 88
    elif damage == "response":
        cassette.boundaries[3].response = {"price": 1}
    elif damage == "fingerprint":
        cassette.fingerprint = "0" * 64
    else:
        cassette.boundaries.pop()
    with pytest.raises(Divergence):
        validate(cassette)
    assert not verify(cassette, make_demo_run(), 1).passed


def test_recording_roundtrip_and_envelope_corruption(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    child = recover_demo(record_demo())
    export_run(child, path)
    assert import_run(path) == child
    data = json.loads(path.read_text())
    data["run"]["final_output"] = "forged"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="checksum"):
        import_run(path)


def test_store_lineage_and_atomic_rollback(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.db")
    child = recover_demo(record_demo())
    rid = store.save(child)
    assert store.load(rid) == child
    broken = copy.deepcopy(child)
    broken.metadata["not_json"] = object()
    with pytest.raises(TypeError):
        store.save(broken)
    assert len(store.list_runs()) == 1
    store.close()


def test_state_never_leaks_future_output() -> None:
    c = record_demo()
    earlier = state_at(c, 2)
    assert earlier["agent_snapshot"] is None
    assert "tool:price_lookup" not in earlier["observed"]
    assert earlier["final_output"] is None
    assert state_at(c, 4)["agent_snapshot"]["quoted_price"] == 720
    assert state_at(c, 6)["final_output"] == c.final_output


def test_matching_boundaries_with_changed_output_diverge() -> None:
    a = record_demo()
    b = copy.deepcopy(a)
    b.final_output = "changed agent logic"
    result = first_divergence(a, b)
    assert result.diverged and "final outputs" in result.reason


def test_socket_guard_blocks_and_restores() -> None:
    original = socket.socket.connect
    with pytest.raises(NetworkBlocked), offline_guard(), socket.socket() as sock:
        sock.connect(("127.0.0.1", 9))
    assert socket.socket.connect is original


def test_replay_flags_unmediated_socket_attempt() -> None:
    def unsafe(session: Session, inner: httpx.BaseTransport | None) -> str:
        with socket.socket() as sock:
            sock.connect(("127.0.0.1", 9))
        return ""

    result = verify(Cassette(), unsafe, 1)
    assert not result.passed and "socket" in result.detail


def test_utf8_split_across_frames_and_content_type() -> None:
    raw = 'data: {"text":"नमस्ते"}\n\n'.encode()
    frames = [raw[:17], raw[17:]]
    session = Session("record")
    transport = RecordingTransport(
        session,
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=iter(frames)
            )
        ),
    )
    with httpx.Client(transport=transport) as client:
        response = client.get("https://demo.invalid/events")
        assert response.content == raw
        assert response.headers["content-type"] == "text/event-stream"


def test_sensitive_named_fields_are_redacted() -> None:
    assert redact({"password": "tiny", "nested": {"api_key": "abc"}}) == {
        "password": "<redacted:field>",
        "nested": {"api_key": "<redacted:field>"},
    }


def test_dashboard_cannot_embed_script_from_prompt(tmp_path: Path) -> None:
    output = tmp_path / "desk.html"
    c = record_demo()
    c.final_output = '</script><script>alert("injection")</script>'
    render_dashboard({"untrusted <script>": c}, output)
    html = output.read_text()
    assert c.final_output not in html
    assert "\\u003c/script\\u003e" in html
    assert "connect-src 'none'" in html


def test_script_recording_stdout_and_source_drift(tmp_path: Path) -> None:
    path = tmp_path / "agent.py"
    path.write_text(
        'import httpx\nwith httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"answer": 42}))) as c:\n    print(c.get("https://demo.invalid/task").json()["answer"])\n'
    )
    cassette = record_script(path)
    assert cassette.final_output == "42\n"
    assert len(cassette.boundaries) == 1
    assert verify_script(cassette, path, 5).passed
    path.write_text('print("changed")\n')
    with pytest.raises(ValueError, match="source differs"):
        verify_script(cassette, path)


def test_cli_demo_export_import_fork_and_eval(tmp_path: Path) -> None:
    runner = CliRunner()
    db, output = str(tmp_path / "runs.db"), tmp_path / "demo.html"
    result = runner.invoke(app, ["demo", "--n", "2", "--db", db, "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert output.exists()
    store = RunStore(db)
    runs = store.list_runs()
    assert len(runs) == 3
    rid = runs[0].id
    store.close()
    for args in (
        ["show", rid, "--at", "3"],
        ["verify", rid, "--n", "2"],
        ["fork", rid, "--price", "400"],
        ["similar", rid],
    ):
        result = runner.invoke(app, [*args, "--db", db])
        assert result.exit_code == 0, result.output
    path = tmp_path / "export.json"
    assert runner.invoke(app, ["export", rid, str(path), "--db", db]).exit_code == 0
    assert runner.invoke(app, ["import", str(path), "--db", db]).exit_code == 0
    assert runner.invoke(app, ["eval", "--n", "2"]).exit_code == 0
    assert runner.invoke(app, ["verify", rid, "--n", "0", "--db", db]).exit_code != 0


def test_similarity_identity_and_empty() -> None:
    c = record_demo()
    assert similarity(c, c) == pytest.approx(1)
    assert similarity(Cassette(), c) == 0


def test_zero_replays_rejected() -> None:
    with pytest.raises(ValueError):
        verify(record_demo(), make_demo_run(), 0)
