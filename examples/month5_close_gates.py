"""Close leftover Month 5 gates using Gemini or NVIDIA when a key is set.

Writes docs/validation/month5/course-close.json. OpenAI/Anthropic are not used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flightrecorder.month5 import close_month5_gates


def main() -> None:
    live = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("NVIDIA_API_KEY"))
    report = close_month5_gates(10, live=live)
    out = Path("docs/validation/month5/course-close.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
