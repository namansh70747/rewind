"""Redaction-on-write: scrub secrets/PII from bodies BEFORE they enter a recording.

Recordings can contain prompts, tool args, and responses that carry API keys, tokens, or
PII (risk R6 in ``docs/plan/risks-and-spikes.md``). Redaction runs at *capture* time, so the
raw secret never reaches the boundary log or the store — never capture-then-scrub.

Replacements are **deterministic** (a fixed ``<redacted:name>`` placeholder), so record and
replay produce identical redacted content and the hash-chain stays consistent.

Scope: request *headers* are already not captured (so ``Authorization`` never lands here);
this covers secrets embedded in URLs and bodies. It is a pragmatic pattern set, not a
guarantee — a structure-only capture mode and richer detectors come later.
"""

from __future__ import annotations

import re
from typing import Any

# Order matters: more specific patterns first (e.g. sk-ant- before the generic sk-).
# Leading lookbehind avoids matching mid-token noise (e.g. random base64 containing "sk-").
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic-key", re.compile(r"(?<![A-Za-z0-9_\-])sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(r"(?<![A-Za-z0-9_\-])sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("nvidia-key", re.compile(r"(?<![A-Za-z0-9_\-])nvapi-[A-Za-z0-9_\-]{20,}")),
    ("google-key", re.compile(r"(?<![A-Za-z0-9_\-])AIza[A-Za-z0-9_\-]{30,}")),
    ("aws-key", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"(?<![A-Za-z0-9_\-])gh[posru]_[A-Za-z0-9]{20,}")),
    ("slack-token", re.compile(r"(?<![A-Za-z0-9_\-])xox[baprs]-[A-Za-z0-9\-]{10,}")),
    (
        "jwt",
        re.compile(
            r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
        ),
    ),
    ("bearer", re.compile(r"(?i)(?<![A-Za-z0-9_\-])bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
]


def redact_text(text: str) -> str:
    """Replace any known secret/PII pattern in ``text`` with a deterministic placeholder."""
    for name, pattern in _PATTERNS:
        text = pattern.sub(f"<redacted:{name}>", text)
    return text


def redact(obj: Any) -> Any:
    """Recursively redact all strings in a JSON-like structure, returning a new value."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {key: redact(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [redact(value) for value in obj]
    if isinstance(obj, tuple):
        return tuple(redact(value) for value in obj)
    return obj
