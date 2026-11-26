"""Record the course Month 2 live corpus with NVIDIA and/or Gemini only.

Each configured key records two controlled agents (six model calls) and 50
offline replays. Recordings stay under .rewind/month2-corpus/; the summary JSON
is copied to docs/validation/month2/course-close.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from flightrecorder.providers import GEMINI, NVIDIA

ROOT = Path(__file__).resolve().parents[1]


def _run(provider: str, model: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "provider_corpus.py"),
            provider,
            model,
            "--runs",
            "2",
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
    report_path = output / "qualification.json"
    payload = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    payload["exit_code"] = proc.returncode
    if proc.returncode != 0:
        payload["stderr"] = proc.stderr[-2000:]
    return payload


def main() -> None:
    evidence: dict[str, Any] = {"schema": "rewind.month2-course-close.v1", "providers": {}}
    dest = ROOT / ".rewind" / "month2-corpus"
    dest.mkdir(parents=True, exist_ok=True)
    published = ROOT / "docs" / "validation" / "month2"
    published.mkdir(parents=True, exist_ok=True)
    if os.environ.get(NVIDIA.key_env):
        evidence["providers"]["nvidia"] = _run("nvidia", NVIDIA.default_model, dest / "nvidia")
    if os.environ.get(GEMINI.key_env):
        evidence["providers"]["gemini"] = _run("gemini", GEMINI.default_model, dest / "gemini")
    if not evidence["providers"]:
        evidence["passed"] = False
        evidence["detail"] = "configure NVIDIA_API_KEY and/or GEMINI_API_KEY locally"
    else:
        evidence["passed"] = all(bool(row.get("passed")) for row in evidence["providers"].values())
    out = published / "course-close.json"
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    raise SystemExit(0 if evidence.get("passed") else 1)


if __name__ == "__main__":
    main()
