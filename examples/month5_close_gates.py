"""Close the course Month 5 leftover gates without paid OpenAI/Anthropic keys.

Writes docs/validation/month5/course-close.json. No live LLM is called.
"""

from __future__ import annotations

import json
from pathlib import Path

from flightrecorder.month5 import close_month5_gates


def main() -> None:
    report = close_month5_gates(10)
    out = Path("docs/validation/month5/course-close.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
