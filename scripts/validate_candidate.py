"""Run local acceptance checks once and preserve logs separately from release gates.

Usage: uv sync --frozen --extra dev --extra docs --extra integrations --extra tui --extra ml
       uv run python scripts/validate_candidate.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / ".rewind" / "acceptance"
    output.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    checks = [
        ("lint", [python, "-m", "ruff", "check", "."]),
        ("format", [python, "-m", "ruff", "format", "--check", "."]),
        ("types", [python, "-m", "mypy"]),
        ("tests", [python, "-m", "pytest", "--cov", "--cov-report=term-missing"]),
        ("docs", [python, "-m", "mkdocs", "build", "--strict"]),
        ("build", ["uv", "build"]),
        ("wheel", [python, "scripts/wheel_smoke.py"]),
    ]
    results = []
    for name, command in checks:
        start = time.monotonic()
        try:
            with (output / f"{name}.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=600
                )
            code, detail = process.returncode, "see log"
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, detail = 1, str(exc)
        results.append(
            {
                "check": name,
                "passed": code == 0,
                "seconds": round(time.monotonic() - start, 3),
                "detail": detail,
            }
        )
        print(f"{'PASS' if code == 0 else 'FAIL'}: {name}", flush=True)
    release = subprocess.run(
        [
            python,
            "-m",
            "flightrecorder.cli",
            "release-check",
            "docs/release-evidence/checklist.json",
            "--output",
            str(output / "release.json"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    (output / "release.log").write_text(release.stdout + release.stderr, encoding="utf-8")
    report = {
        "local_checks_passed": all(row["passed"] for row in results),
        "release_check_passed": release.returncode == 0,
        "checks": results,
        "scope": "Local candidate only; live corpora, models, browser and remote CI need their separate evidence.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Release evidence: " + ("complete" if report["release_check_passed"] else "BLOCKED"))
    print(output / "report.json")
    raise SystemExit(0 if report["local_checks_passed"] else 1)


if __name__ == "__main__":
    main()
