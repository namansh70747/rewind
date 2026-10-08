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


def query(cassette: Cassette, expression: str) -> list[dict[str, Any]]:
    """Examples: `kind == "tool"`, `first response.status >= 400`."""
    match = _PATTERN.fullmatch(expression)
    if not match:
        raise ValueError("query syntax: [first] field.path OP JSON_VALUE")
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
