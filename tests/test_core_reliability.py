from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from io import BytesIO, StringIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from typer.testing import CliRunner

from flightrecorder.boundary import canon
from flightrecorder.cli import app
from flightrecorder.diagnosis import diagnose
from flightrecorder.integrity import IntegrityError
from flightrecorder.portable import envelope, import_run
from flightrecorder.product.server import Handler
from flightrecorder.product.worker import main as run_worker
from flightrecorder.redaction import RedactionRules, redaction_rules
from flightrecorder.scripts import record_script, verify_script
from flightrecorder.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("statement", "code"),
    [("sys.exit()", 0), ("sys.exit(0)", 0), ("sys.exit(2)", 2), ("sys.exit('failed')", 1)],
)
def test_record_script_persists_system_exit(tmp_path: Path, statement: str, code: int) -> None:
    source = tmp_path / "agent.py"
    source.write_text("import sys\n" + statement + "\n", encoding="utf-8")
    db = tmp_path / "runs.db"
    result = CliRunner().invoke(app, ["record-script", str(source), "--db", str(db)])
    assert result.exit_code == code, result.output
    store = RunStore(db)
    try:
        (summary,) = store.list_runs()
        assert summary.id in result.output
        run = store.load_validated(summary.id)
        assert run.metadata["terminal_outcome"]["code"] == code
        assert verify_script(run, source, 3).passed
    finally:
        store.close()


def test_verify_failure_prefix_and_terminal_drift(tmp_path: Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text(
        "import os\nfrom flightrecorder.tools import tool\n"
        "@tool\ndef read(value):\n    return value\n"
        "print(read('first'))\n"
        "if os.environ.get('REWIND_TEST_SKIP') != 'second':\n    read('second')\n"
        "if os.environ.get('REWIND_TEST_FAIL') == 'yes':\n    raise ValueError('private-value')\n",
        encoding="utf-8",
    )
    with (
        pytest.MonkeyPatch.context() as env,
        redaction_rules(RedactionRules(literals=("private-value",))),
    ):
        env.setenv("REWIND_TEST_FAIL", "yes")
        failed = record_script(source)
        assert failed.final_output == "first\n"
        assert len(failed.boundaries) == 2
        assert failed.metadata["terminal_outcome"]["kind"] == "exception"
        assert "private-value" not in json.dumps(envelope(failed))
        assert verify_script(failed, source, 50).passed

        env.setenv("REWIND_TEST_FAIL", "no")
        healthy = record_script(source)
        assert healthy.fingerprint == failed.fingerprint
        assert diagnose(failed, healthy)["primary_difference"]["label"] == "final-outcome-drift"
        assert "terminal outcome" in str(verify_script(failed, source, 1))
        env.setenv("REWIND_TEST_SKIP", "second")
        early = verify_script(failed, source, 1)
        assert not early.passed
        assert "boundary #1" in str(early)


def test_shared_integrity_and_portable_execution_link(tmp_path: Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text(
        "from flightrecorder.tools import tool\n"
        "@tool\ndef value():\n    return 'captured'\n"
        "print(value())\n",
        encoding="utf-8",
    )
    cassette = record_script(source)
    cassette.metadata["product_source"] = str(source)
    bundle = envelope(cassette)
    assert "product_source" not in bundle["run"]["metadata"]
    assert cassette.metadata["product_source"] == str(source)
    bundle["run"]["metadata"]["product_source"] = str(source)
    bundle["checksum"] = hashlib.sha256(canon(bundle["run"])).hexdigest()
    path = tmp_path / "legacy.rewind"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert "product_source" not in import_run(path).metadata

    db = tmp_path / "runs.db"
    store = RunStore(db)
    try:
        run_id = store.save(cassette)
        with store.conn:
            store.conn.execute(
                "UPDATE boundary SET chain_hash = 'damaged' WHERE run_id = ?", (run_id,)
            )
        with pytest.raises(IntegrityError, match="boundary #0"):
            store.load_validated(run_id)

        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(db=db, server_port=8766, token="test")  # type: ignore[assignment]
        responses: list[tuple[int, Any]] = []
        handler._json = lambda value, status=200: responses.append((status, value))  # type: ignore[method-assign]
        handler.path = f"/api/v1/runs/{run_id}"
        handler.headers = {"Host": "127.0.0.1:8766"}  # type: ignore[assignment]
        handler.do_GET()
        assert responses[-1][0] == 422
        assert responses[-1][1]["code"] == "recording_integrity"
        assert responses[-1][1]["boundary"] == 0

        with store.conn:
            store.conn.execute(
                "CREATE TABLE product_verification (run_id TEXT, passed INT, replays INT, checked_at REAL)"
            )
        healthy_id = store.save(cassette)
        handler.path = "/api/v1/runs"
        handler.do_GET()
        assert responses[-1][0] == 200
        entries = {entry["id"]: entry for entry in responses[-1][1]["runs"]}
        assert entries[run_id]["integrity_error"]
        assert "integrity_error" not in entries[healthy_id]

        handler.path = "/api/v1/export"
        data = json.dumps({"run_id": run_id}).encode()
        handler.rfile = BytesIO(data)
        handler.headers["Content-Length"] = str(len(data))
        handler.headers["X-Rewind-Token"] = "test"
        handler.do_POST()
        assert responses[-1][0] == 422
        result = CliRunner().invoke(app, ["show", run_id, "--db", str(db)])
        assert result.exit_code == 1
        assert "recording corrupted" in result.output
        assert "captured" not in result.output
        with store.conn:
            store.conn.execute("UPDATE blob SET data = X'00'")
        with pytest.raises(IntegrityError, match="payload missing or corrupt"):
            store.load_validated(run_id)
    finally:
        store.close()


def test_workspace_worker_forks_without_executing_the_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = tmp_path / "tool-effects.txt"
    source = tmp_path / "agent.py"
    source.write_text(
        "from pathlib import Path\nfrom flightrecorder.tools import tool\n"
        "@tool\ndef read():\n"
        f"    with Path({str(marker)!r}).open('a') as stream:\n        stream.write('x')\n"
        "    return 'bad'\n"
        "answer = read()\nprint(answer)\n"
        "if answer == 'bad':\n    raise ValueError('invalid answer')\n",
        encoding="utf-8",
    )
    db = tmp_path / "runs.db"
    request: dict[str, Any] = {"db": str(db), "source": str(source), "action": "capture"}
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(request)))
    run_worker()
    captured = json.loads(capsys.readouterr().out)
    parent_id = captured["result"]["run_id"]
    assert captured["result"]["terminal_outcome"]["code"] == 1
    request.update(
        action="fork",
        run_id=parent_id,
        intervention={"at": 0, "value": {"ok": True, "value": "good"}},
    )
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(request)))
    run_worker()
    result = json.loads(capsys.readouterr().out)
    assert result["ok"], result
    store = RunStore(db)
    try:
        parent = store.load_validated(parent_id)
        child = store.load_validated(result["result"]["run_id"])
        assert parent.final_output == "bad\n"
        assert child.final_output == "good\n"
        assert child.metadata["parent_run"] == parent_id
        assert child.metadata["parent_fingerprint"] == parent.fingerprint
        assert child.metadata["terminal_outcome"]["code"] == 0
        assert marker.read_text(encoding="utf-8") == "x"
    finally:
        store.close()


def test_checkpoint_survives_process_loss(tmp_path: Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text(
        "import os\nfrom flightrecorder import tool\n"
        "@tool\ndef read():\n    return 'committed prefix'\n"
        "read()\nos._exit(23)\n",
        encoding="utf-8",
    )
    db = tmp_path / "runs.db"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from flightrecorder.cli import main; main()",
            "record-script",
            str(source),
            "--db",
            str(db),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 23, result.stdout + result.stderr
    store = RunStore(db)
    try:
        (entry,) = store.list_runs()
        recovered = store.load_validated(entry.id)
        assert recovered.metadata["capture_status"] == "incomplete"
        assert recovered.metadata["replayable"] is False
        assert recovered.boundaries[0].response["value"] == "committed prefix"
        assert "terminal_outcome" not in recovered.metadata
        with pytest.raises(ValueError, match="incomplete captures"):
            verify_script(recovered, source, 1)
        shown = CliRunner().invoke(app, ["show", entry.id, "--db", str(db)])
        assert shown.exit_code == 0
        assert "Incomplete capture" in shown.output
    finally:
        store.close()
