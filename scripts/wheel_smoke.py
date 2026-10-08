"""Install a built wheel into a fresh environment and run its offline demo.

Cross-platform and stdlib-only. Run after `uv build`; no editable-install imports.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = list((root / "dist").glob("rewind-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one Rewind wheel in dist/; clean stale builds first")
    output = root / ".rewind" / "wheel-smoke"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rewind-wheel-") as temporary:
        env = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(env)
        scripts = env / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        cli = scripts / ("fr.exe" if os.name == "nt" else "fr")
        clean_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
        commands = [
            [str(python), "-m", "pip", "install", str(wheels[0])],
            [str(cli), "--help"],
            [str(cli), "demo", "--n", "50", "--output", str(output / "demo.html")],
            [str(cli), "eval", "--n", "2", "--output", str(output / "evaluation.json")],
        ]
        for command in commands:
            result = subprocess.run(
                command, cwd=temporary, env=clean_env, text=True, capture_output=True, timeout=300
            )
            print(result.stdout)
            if result.returncode:
                print(result.stderr, file=sys.stderr)
                raise SystemExit(result.returncode)
    (output / "platform.json").write_text(
        json.dumps({"platform": sys.platform, "python": sys.version, "passed": True}, indent=2),
        encoding="utf-8",
    )
    print("PASS: clean wheel, console script, 150 demo replays and evaluation")


if __name__ == "__main__":
    main()
