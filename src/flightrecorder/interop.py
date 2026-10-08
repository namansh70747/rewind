"""Perfetto Trace Event and OTLP/HTTP JSON export; trace-only ingest is not replay."""

from __future__ import annotations

import base64
import hashlib
import json
from functools import partial
from typing import TYPE_CHECKING, Any

from .boundary import Cassette, Session, canon
from .integrity import validate
from .redaction import redact

if TYPE_CHECKING:
    from pathlib import Path


def perfetto(cassette: Cassette) -> dict[str, Any]:
    validate(cassette)
    return {
        "displayTimeUnit": "ms",
        "traceEvents": [
            {
                "name": b.key,
                "cat": b.kind,
                "ph": "i",
                "s": "t",
                "ts": b.seq,
                "pid": 1,
                "tid": 1,
                "args": {
                    "sequence": b.seq,
                    "request": b.request,
                    "response": b.response,
                    "chain_hash": b.chain_hash,
                    "time_basis": "ordinal (not wall time)",
                },
            }
            for b in cassette.boundaries
        ],
    }


def otlp(cassette: Cassette) -> dict[str, Any]:
    validate(cassette)
    trace = hashlib.sha256(canon([cassette.fingerprint, cassette.final_output])).hexdigest()[:32]
    spans = []
    for b in cassette.boundaries:
        attributes: dict[str, Any] = {
            "rewind.sequence": b.seq,
            "rewind.chain_hash": b.chain_hash,
            "rewind.kind": b.kind,
            "rewind.time_basis": "ordinal",
            "input.value": json.dumps(b.request),
            "output.value": json.dumps(b.response),
            "openinference.span.kind": {"llm": "LLM", "tool": "TOOL"}.get(b.kind, "CHAIN"),
        }
        spans.append(
            {
                "traceId": trace,
                "spanId": f"{b.seq + 1:016x}",
                "name": b.key,
                "kind": 1,
                "startTimeUnixNano": str(1_000_000_000 + b.seq * 1000),
                "endTimeUnixNano": str(1_000_000_000 + b.seq * 1000 + 1),
                "attributes": [
                    {
                        "key": key,
                        "value": {"intValue": str(value)}
                        if isinstance(value, int)
                        else {"stringValue": value},
                    }
                    for key, value in attributes.items()
                ],
                "status": {"code": 0},
            }
        )
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "rewind"}}]
                },
                "scopeSpans": [
                    {"scope": {"name": "flightrecorder", "version": "0.1.0"}, "spans": spans}
                ],
            }
        ]
    }


def otlp_protobuf(cassette: Cassette) -> bytes:
    """Standard OTLP protobuf for collectors that reject OTLP/HTTP JSON."""
    from google.protobuf.json_format import ParseDict
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    data = otlp(cassette)
    # OTLP JSON uses hex IDs; protobuf's generic JSON parser expects base64 bytes.
    for resource in data["resourceSpans"]:
        for scope in resource["scopeSpans"]:
            for span in scope["spans"]:
                for key in ("traceId", "spanId"):
                    span[key] = base64.b64encode(bytes.fromhex(span[key])).decode("ascii")
    message = ExportTraceServiceRequest()
    ParseDict(data, message)
    return message.SerializeToString()


def ingest_otlp(data: dict[str, Any]) -> Cassette:
    """Import viewer evidence. External traces lack complete boundary values/schedule."""
    session = Session("record")
    for resource in data.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                safe = redact(span)
                session.mediate(
                    "trace",
                    str(safe.get("name", "unnamed")),
                    None,
                    partial(lambda value: value, safe),
                )
    return Cassette(
        session.boundaries,
        session.chain,
        "",
        "otel",
        "imported-trace",
        {
            "replayable": False,
            "reason": "External spans are observational, not complete replay recordings.",
        },
    )


def write_trace(cassette: Cassette, path: Path, format: str) -> None:
    if format not in {"perfetto", "otlp", "otlp-protobuf"}:
        raise ValueError("format must be perfetto, otlp or otlp-protobuf")
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "otlp-protobuf":
        path.write_bytes(otlp_protobuf(cassette))
        return
    path.write_text(
        json.dumps(perfetto(cassette) if format == "perfetto" else otlp(cassette), indent=2),
        encoding="utf-8",
    )
