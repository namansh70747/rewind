"""Structured JSON differences and logical decision views, retaining raw evidence."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from .boundary import canon

if TYPE_CHECKING:
    from .boundary import Boundary


def similarity(a: Any, b: Any) -> float:
    if type(a) is type(b) and canon(a) == canon(b):
        return 1.0
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        return sum(similarity(a[k], b[k]) for k in keys if k in a and k in b) / max(1, len(keys))
    if isinstance(a, list) and isinstance(b, list):
        return sum(similarity(x, y) for x, y in zip(a, b, strict=False)) / max(1, len(a), len(b))
    if type(a) in (int, float) and type(b) in (int, float):
        return float(max(0.0, 1 - abs(a - b) / max(1, abs(a), abs(b))))
    if isinstance(a, str) and isinstance(b, str):
        return SequenceMatcher(
            None, a.casefold().split(), b.casefold().split(), autojunk=False
        ).ratio()
    return 0.0


def json_diff(a: Any, b: Any, path: str = "", *, limit: int = 500) -> list[dict[str, Any]]:
    """JSON-pointer changes; missing and explicit null remain distinguishable."""
    changes: list[dict[str, Any]] = []

    def visit(left: Any, right: Any, pointer: str) -> None:
        if len(changes) >= limit:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key not in left or key not in right:
                    changes.append(
                        {
                            "path": child,
                            "before_present": key in left,
                            "after_present": key in right,
                            "before": left.get(key),
                            "after": right.get(key),
                        }
                    )
                else:
                    visit(left[key], right[key], child)
                if len(changes) >= limit:
                    break
        elif type(left) is not type(right) or canon(left) != canon(right):
            changes.append(
                {
                    "path": pointer or "/",
                    "before_present": True,
                    "after_present": True,
                    "before": left,
                    "after": right,
                }
            )

    visit(a, b, path)
    return changes


def logical(boundary: Boundary) -> tuple[str, str, Any, Any, str]:
    """Strip scheduling wrappers for matching, never from the saved raw boundary."""
    kind, key, request, response = boundary.kind, boundary.key, boundary.request, boundary.response
    phase = ""
    if kind.startswith("async-") and isinstance(request, dict) and "kind" in request:
        phase = kind
        kind, key, request = request["kind"], request["key"], request["request"]
    if kind == "mcp" and isinstance(request, dict):
        params = request.get("params", {})
        if request.get("method") == "tools/call" or key.endswith("/tools/call"):
            name = params.get("name", "unknown")
            server = key.removesuffix("/tools/call")
            key = f"{server}/{name}" if key.endswith("/tools/call") else key
            request = params.get("arguments", {})
        else:
            request = {k: v for k, v in request.items() if k != "occurrence"}
        if isinstance(response, dict) and "ok" in response:
            response = {k: v for k, v in response.items() if k != "wire"}
        elif isinstance(response, dict) and "jsonrpc" in response:
            response = {k: v for k, v in response.items() if k not in {"id", "jsonrpc"}}
    if kind == "http" and isinstance(response, dict):
        response = dict(response)
        body = response.get("body")
        if isinstance(body, dict) and isinstance(body.get("json"), dict):
            data = dict(body["json"])
            if "choices" in data:
                for field in ("id", "created", "system_fingerprint"):
                    data.pop(field, None)
                choices = []
                for choice in data["choices"]:
                    item = dict(choice)
                    if isinstance(item.get("message"), dict):
                        item["message"] = {
                            k: v for k, v in item["message"].items() if k != "extra_content"
                        }
                    choices.append(item)
                data["choices"] = choices
                response["body"] = {**body, "json": data}
    return kind, key, request, response, phase


def decision(boundary: Boundary) -> bool:
    kind, key, _, _, phase = logical(boundary)
    if phase == "async-start":
        return False
    return kind in {"tool", "llm", "http"} or (
        kind == "mcp" and not key.endswith(("/initialize", "/tools/list"))
    )


def values_named(value: Any, names: set[str]) -> list[Any]:
    if isinstance(value, dict):
        return [v for k, v in value.items() if k in names] + [
            item for v in value.values() for item in values_named(v, names)
        ]
    if isinstance(value, list):
        return [item for v in value for item in values_named(v, names)]
    return []
