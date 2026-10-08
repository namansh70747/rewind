"""Versioned, checksummed JSON recordings; no pickle or executable payloads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .boundary import Boundary, Cassette, canon
from .integrity import validate

if TYPE_CHECKING:
    from pathlib import Path

FORMAT = "rewind.cassette.v2"
MAX_BYTES = 32 * 1024 * 1024


def envelope(cassette: Cassette) -> dict[str, Any]:
    validate(cassette)
    data = asdict(cassette)
    return {"format": FORMAT, "checksum": hashlib.sha256(canon(data)).hexdigest(), "run": data}


def export_run(cassette: Cassette, path: Path) -> None:
    """Export recorded data as-is. Review prompts before sharing; checksums aren't signatures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope(cassette), indent=2, ensure_ascii=False), encoding="utf-8")


def import_run(path: Path) -> Cassette:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("recording exceeds 32 MiB import limit")
    obj = json.loads(path.read_text(encoding="utf-8"))
    try:
        if obj["format"] not in {FORMAT, "rewind.cassette.v1"}:
            raise ValueError("unsupported recording format")
        data = obj["run"]
        if hashlib.sha256(canon(data)).hexdigest() != obj["checksum"]:
            raise ValueError("recording checksum mismatch")
        if not isinstance(data["boundaries"], list):
            raise ValueError("boundaries must be a list")
        if "chain_algorithm" not in data:
            data["chain_algorithm"] = "blake2b"
        cassette = Cassette(**{**data, "boundaries": [Boundary(**b) for b in data["boundaries"]]})
        if not all(
            isinstance(v, str)
            for v in (
                cassette.final_output,
                cassette.provider,
                cassette.model,
                cassette.fingerprint,
            )
        ):
            raise ValueError("invalid recording metadata")
        if not isinstance(cassette.metadata, dict):
            raise ValueError("metadata must be an object")
        for b in cassette.boundaries:
            if type(b.seq) is not int or not isinstance(b.kind, str) or not isinstance(b.key, str):
                raise ValueError("invalid boundary schema")
        validate(cassette)
        return cassette
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid recording schema") from exc
