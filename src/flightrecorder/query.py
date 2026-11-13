"""Tiny safe timeline query DSL; no eval, code execution or SQL interpolation."""

from __future__ import annotations

import json
import operator
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .boundary import Cassette

_PATTERN = re.compile(r"^\s*(first\s+)?([A-Za-z_][\w.]*)\s*(==|!=|>=|<=|>|<|contains)\s*(.+?)\s*$")
_TOOL_ERROR = re.compile(r"^(?:every\s+)?tool(?:[\s-]error|\s+error)$", re.IGNORECASE)
_RETRY = re.compile(r"^(?:every\s+)?retr(?:y|ies)$", re.IGNORECASE)
_CONTEXT = re.compile(
    r"^first\s+(?:time\s+)?(?:context|tokens)\s*>\s*(\d+)\s*(?:tokens)?$",
    re.IGNORECASE,
)


def _rows(cassette: Cassette) -> list[dict[str, Any]]:
    return [asdict(boundary) for boundary in cassette.boundaries]


def _is_tool_error(row: dict[str, Any]) -> bool:
    if row.get("kind") not in {"tool", "mcp"}:
        return False
    response = row.get("response")
    if not isinstance(response, dict):
        return False
    status = response.get("status")
    return bool(
        response.get("ok") is False
        or (isinstance(status, int) and status >= 400)
        or response.get("error")
    )


def _is_retry(row: dict[str, Any]) -> bool:
    request = row.get("request")
    attempt = request.get("attempt") if isinstance(request, dict) else None
    return type(attempt) is int and attempt > 1


def _context_tokens(row: dict[str, Any]) -> int | None:
    response = row.get("response")
    if not isinstance(response, dict):
        return None
    direct = response.get("context_tokens")
    if type(direct) is int and direct >= 0:
        return direct
    body = response.get("body")
    payload = body.get("json") if isinstance(body, dict) else None
    usage = payload.get("usage") if isinstance(payload, dict) else response.get("usage")
    if not isinstance(usage, dict):
        return None
    total = 0
    found = False
    for name in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens"):
        value = usage.get(name)
        if type(value) is int and value >= 0:
            total += value
            found = True
    return total if found else None


def _preset(cassette: Cassette, expression: str) -> list[dict[str, Any]] | None:
    text = expression.strip()
    rows = _rows(cassette)
    if _TOOL_ERROR.fullmatch(text):
        return [row for row in rows if _is_tool_error(row)]
    if _RETRY.fullmatch(text):
        return [row for row in rows if _is_retry(row)]
    context = _CONTEXT.fullmatch(text)
    if context:
        limit = int(context.group(1))
        for row in rows:
            tokens = _context_tokens(row)
            if tokens is not None and tokens > limit:
                return [row]
        return []
    return None


def query(cassette: Cassette, expression: str) -> list[dict[str, Any]]:
    """Examples: `kind == "tool"`, `every tool error`, `first context > 400 tokens`."""
    preset = _preset(cassette, expression)
    if preset is not None:
        return preset
    match = _PATTERN.fullmatch(expression)
    if not match:
        raise ValueError(
            "query syntax: [first] field.path OP JSON_VALUE, "
            "'every tool error', 'every retry', or 'first context > N tokens'"
        )
    first, path, op, literal = match.groups()
    try:
        expected = json.loads(literal)
    except json.JSONDecodeError as exc:
        raise ValueError('values must be JSON, e.g. "tool" or 400') from exc
    result = []
    for b in cassette.boundaries:
        row = asdict(b)
        value: Any = row
        for key in path.split("."):
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        try:
            operations: dict[str, Callable[[Any, Any], bool]] = {
                "==": operator.eq,
                "!=": operator.ne,
                ">=": operator.ge,
                "<=": operator.le,
                ">": operator.gt,
                "<": operator.lt,
                "contains": operator.contains,
            }
            matched = operations[op](value, expected)
        except (TypeError, ValueError):
            matched = False
        if matched:
            result.append(row)
            if first:
                break
    return result
