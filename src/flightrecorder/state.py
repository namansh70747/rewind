"""Versioned, JSON-only logical-state serialization; never executable pickle."""

from __future__ import annotations

import json
from typing import Any

from .boundary import canon
from .redaction import redact

SCHEMA = "rewind.logical-state"
VERSION = 1


def logical_state(value: Any) -> Any:
    """Normalize declared model fields and JSON values, rejecting opaque objects."""
    if hasattr(value, "model_dump"):
        return logical_state(value.model_dump(mode="json"))
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("logical-state mapping keys must be strings")
        return {key: logical_state(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [logical_state(item) for item in value]
    if value is None or type(value) in (str, bool, int, float):
        # canon rejects non-finite numbers and preserves Unicode deterministically.
        return json.loads(canon(value))
    raise ValueError(f"unsupported logical-state type: {type(value).__name__}")


def encode_state(value: Any) -> dict[str, Any]:
    return {"schema": SCHEMA, "version": VERSION, "value": redact(logical_state(value))}


def decode_state(envelope: Any) -> Any:
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema", "version", "value"}
        or envelope["schema"] != SCHEMA
        or type(envelope["version"]) is not int
        or envelope["version"] != VERSION
    ):
        raise ValueError("unsupported logical-state envelope")
    return logical_state(envelope["value"])
