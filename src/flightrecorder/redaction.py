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
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class RedactionRules:
    extra_keys: frozenset[str] = frozenset()
    literals: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, data: Any) -> RedactionRules:
        if not isinstance(data, dict) or set(data) - {"extra_keys", "literals"}:
            raise ValueError("redaction rules accept extra_keys and literals only")
        for key in ("extra_keys", "literals"):
            if not isinstance(data.get(key, []), list) or any(
                not isinstance(v, str) or not v for v in data.get(key, [])
            ):
                raise ValueError("redaction entries must be non-empty strings in lists")
        return cls(
            frozenset(v.lower() for v in data.get("extra_keys", [])),
            tuple(data.get("literals", [])),
        )


_DEFAULT_RULES = RedactionRules()
_RULES: ContextVar[RedactionRules] = ContextVar("rewind_redaction_rules", default=_DEFAULT_RULES)


@contextmanager
def redaction_rules(rules: RedactionRules) -> Iterator[None]:
    """Additional literal/key rules; configuration is never embedded in recordings."""
    token = _RULES.set(rules)
    try:
        yield
    finally:
        _RULES.reset(token)


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
    rules = _RULES.get()
    for literal in sorted(rules.literals, key=len, reverse=True):
        parts = re.split(r"(<redacted:[^>]*>)", text)
        text = "".join(
            part if index % 2 else part.replace(literal, "<redacted:custom>")
            for index, part in enumerate(parts)
        )
    if rules.extra_keys:
        keys = "|".join(re.escape(key) for key in sorted(rules.extra_keys))
        text = re.sub(
            r'(?i)("(?:' + keys + r')"\s*:\s*)"(?:\\.|[^"\\])*"',
            lambda m: m.group(1) + '"<redacted:field>"',
            text,
        )
    # Quoted JSON/SSE credentials may contain whitespace or escaped quotes. Remove
    # the whole value before pattern matching; a token-only regex can leak its tail.
    text = re.sub(
        r'(?i)("(?:password|passwd|secret|api_key|apikey|access_token|refresh_token|authorization|token|client_secret)"\s*:\s*)"(?:\\.|[^"\\])*"',
        lambda match: match.group(1) + '"<redacted:field>"',
        text,
    )
    # Covers short named credentials in fragments and URL query strings.
    text = re.sub(
        r'(?i)((?:"?(?:password|passwd|api_key|apikey|access_token|refresh_token|client_secret)"?)\s*[:=]\s*"?)(?!<redacted:)([^"\s,&}]+)',
        lambda match: match.group(1) + "<redacted:field>",
        text,
    )
    for name, pattern in _PATTERNS:
        text = pattern.sub(f"<redacted:{name}>", text)
    return text


_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "token",
    "client_secret",
}


def redact(obj: Any) -> Any:
    """Recursively redact all strings in a JSON-like structure, returning a new value."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {
            redact_text(str(key)): "<redacted:field>"
            if str(key).lower() in _SENSITIVE_KEYS | _RULES.get().extra_keys
            else redact(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [redact(value) for value in obj]
    if isinstance(obj, tuple):
        return tuple(redact(value) for value in obj)
    return obj
