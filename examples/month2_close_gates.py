"""Record the course Month 2 live corpus with configured hosted providers.

Each configured key records two controlled agents (six model calls) and 50
offline replays. Recordings stay under .rewind/month2-corpus/; the summary JSON
stays in the requested private output directory. This is a controlled smoke corpus.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from flightrecorder.providers import PROVIDERS
from flightrecorder.redaction import redact_text

ROOT = Path(__file__).resolve().parents[1]


def _run(provider: str, model: str, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "provider_corpus.py"),
            provider,
            model,
            "--runs",
            "2",
            "--max-model-calls",
            "6",
            "--replays",
            "50",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "passed": False,
            "exit_code": proc.returncode,
            "stderr": redact_text(proc.stderr[-2000:]),
        }
    report_path = output / "qualification.json"
    payload = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    payload["exit_code"] = proc.returncode
    return payload


def main() -> None:
    evidence: dict[str, Any] = {"schema": "rewind.month2-course-close.v1", "providers": {}}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-model-calls", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    missing = [
        provider.key_env for provider in PROVIDERS.values() if not os.getenv(provider.key_env)
    ]
    if missing:
        parser.error("missing credentials: " + ", ".join(missing))
    if args.max_model_calls < 6 * len(PROVIDERS):
        parser.error("configured call cap is below the requested smoke corpus")
    dest = args.output.resolve()
    if dest.exists() and any(dest.iterdir()):
        parser.error("choose an empty output directory")
    dest.mkdir(parents=True, exist_ok=True)
    for provider in PROVIDERS.values():
        if os.environ.get(provider.key_env):
            evidence["providers"][provider.name] = _run(
                provider.name, provider.default_model, dest / provider.name
            )
    if not evidence["providers"]:
        evidence["passed"] = False
        evidence["detail"] = "configure provider credentials locally"
    else:
        evidence["passed"] = all(
            bool(row.get("passed")) and row.get("exit_code") == 0
            for row in evidence["providers"].values()
        )
    out = dest / "course-close.json"
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    raise SystemExit(0 if evidence.get("passed") else 1)


if __name__ == "__main__":
    main()
