"""CLI/workflow acceptance for roadmap additions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from flightrecorder import RunStore
from flightrecorder.cli import app
from flightrecorder.demo import record_demo
from flightrecorder.fleet import feature_text, predict_cause, train_classifier
from flightrecorder.portable import export_run
from flightrecorder.scripts import record_script

if TYPE_CHECKING:
    from pathlib import Path


def test_cli_on_legacy_redirected_terminal(tmp_path: Path) -> None:
    """Windows pipes can use cp1252, which cannot represent help/demo arrows."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252:strict"}
    for arguments in (["--help"], ["demo", "--n", "2", "--output", str(tmp_path / "demo.html")]):
        result = subprocess.run(
            [sys.executable, "-m", "flightrecorder.cli", *arguments],
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr.decode("cp1252", errors="replace")
    assert (tmp_path / "demo.html").is_file()


def test_roadmap_cli_commands(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    store = RunStore(db)
    try:
        failed = store.save(record_demo())
        good = store.save(record_demo(420))
    finally:
        store.close()
    runner = CliRunner()
    for command in (
        ["query", failed, 'kind == "tool"'],
        ["snapshot", failed, "5"],
        ["diagnose", failed, good],
        ["storage-stats"],
        ["weak-labels", failed],
    ):
        result = runner.invoke(app, [*command, "--db", str(db)])
        assert result.exit_code == 0, (command, result.output, result.exception)
    assert runner.invoke(app, ["hash-bisect", failed, good, "--db", str(db)]).exit_code == 1
    for format in ("otlp", "perfetto"):
        result = runner.invoke(
            app,
            [
                "trace-export",
                failed,
                str(tmp_path / f"{format}.json"),
                "--format",
                format,
                "--db",
                str(db),
            ],
        )
        assert result.exit_code == 0, result.output
    assert (
        runner.invoke(app, ["trace-import", str(tmp_path / "otlp.json"), "--db", str(db)]).exit_code
        == 0
    )


def test_fixture_gate_and_script_fork(tmp_path: Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text(
        'from flightrecorder import tool\n@tool(name="quote",mutating=False)\ndef quote():\n    return 720\nprint("ok" if quote() <= 500 else "over-budget")\n'
    )
    cassette = record_script(source)
    export_run(cassette, tmp_path / "run.json")
    manifest = tmp_path / "fixtures.json"
    manifest.write_text(json.dumps([{"script": "agent.py", "recording": "run.json"}]))
    runner = CliRunner()
    assert runner.invoke(app, ["eval-fixtures", str(manifest), "--n", "2"]).exit_code == 0
    from flightrecorder.scripts import fork_script, verify_script

    child = fork_script(cassette, source, at=0, value={"ok": True, "value": 420}, mocks={})
    assert child.final_output == "ok\n"
    assert verify_script(child, source, 2).passed
    source.write_text('print("changed")\n')
    result = runner.invoke(app, ["eval-fixtures", str(manifest), "--n", "2"])
    assert result.exit_code == 1


def test_safe_json_classifier_inference() -> None:
    samples = []
    for price in (400, 900):
        for i in range(20):
            samples.append(
                {
                    "text": feature_text(record_demo(price)) + f" unique-{price}-{i}",
                    "label": "pass" if price == 400 else "budget",
                    "group": f"{price}-{i}",
                }
            )
    model = train_classifier(samples)
    # JSON export is both serializable and sufficient for inference; no pickle.
    restored = json.loads(json.dumps(model))
    result = predict_cause(restored, record_demo(900))
    assert result["label"] == "budget"
    assert abs(sum(result["probabilities"].values()) - 1) < 1e-9
