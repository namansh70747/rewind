"""Check roadmap requirement coverage and, on release, completed dispositions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

LEDGER = Path("docs/release-evidence/acceptance-ledger.json")
SOURCE = "c69c590be94d0876d536a9ee0e3fb4ac6cc1f39e"


def expected_requirements() -> set[tuple[str, int]]:
    sources = {
        "roadmap-6-months.md": r"^- \*\*(?:E[123]|All:|Exit criterion)",
        "risks-and-spikes.md": r"^### Spike [A-G]\b",
        "milestones-and-exit-criteria.md": r"^\| M[0-6]\.\d+ \|",
    }
    expected = set()
    for name, pattern in sources.items():
        path = f"docs/plan/{name}"
        original = subprocess.check_output(["git", "show", f"{SOURCE}:{path}"], text=True)
        section = ""
        for number, line in enumerate(original.splitlines(), 1):
            if line.startswith("## "):
                section = line
            final = section.startswith("## The final Definition") and re.match(r"^[1-7]\. ", line)
            kpi = (
                section.startswith("## KPIs ")
                and line.startswith("| ")
                and not line.startswith("| KPI ")
            )
            if re.search(pattern, line) or final or kpi:
                expected.add((path, number))
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-closed", action="store_true")
    args = parser.parse_args()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    if ledger["source_commit"] != SOURCE:
        raise SystemExit("Acceptance ledger points to an unexpected source revision.")
    rows = ledger["requirements"]
    locations = {(row["source"], row["line"]) for row in rows}
    expected = expected_requirements()
    if len(locations) != len(rows) or len({row["id"] for row in rows}) != len(rows):
        raise SystemExit("Duplicate acceptance ledger requirements.")
    if locations != expected:
        raise SystemExit(
            f"Ledger coverage mismatch. Missing: {sorted(expected - locations)}; extra: {sorted(locations - expected)}"
        )
    for row in rows:
        if row["status"] not in {"pending", "blocked", "failed", "passed", "superseded"}:
            raise SystemExit(f"Invalid disposition: {row['id']}")
        if row["status"] in {"passed", "superseded"} and not row["evidence"]:
            raise SystemExit(f"Missing evidence or replacement link: {row['id']}")
    unresolved = [row["id"] for row in rows if row["status"] not in {"passed", "superseded"}]
    print(f"{len(rows)} original requirements tracked; {len(unresolved)} unresolved.")
    if args.require_closed and unresolved:
        raise SystemExit("Release blocked by unresolved acceptance ledger requirements.")


if __name__ == "__main__":
    main()
