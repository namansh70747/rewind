"""Close leftover Month 5 gates with synthetic fixtures; approval remains pending.

Writes docs/validation/month5/course-close.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flightrecorder.month5 import close_month5_gates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Opt in to billed xAI baseline calls")
    args = parser.parse_args()
    report = close_month5_gates(10, live=args.live)
    out = Path("docs/validation/month5/course-close.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
