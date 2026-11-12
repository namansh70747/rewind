"""Send unmodified Month 3 OTLP exports to Jaeger and verify stored evidence."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path)
    parser.add_argument("--collector", default="http://127.0.0.1:4318/v1/traces")
    parser.add_argument("--query", default="http://127.0.0.1:16686")
    parser.add_argument("--output", type=Path, default=Path(".rewind/jaeger-report.json"))
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    exports = sorted(args.recordings.glob("*.otlp"))
    if not exports:
        parser.error("No OTLP JSON exports found")
    reports = []
    with httpx.Client(timeout=10, trust_env=False) as client:
        # Wait for both UI and collector startup. Every retry is bounded.
        for attempt in range(30):
            try:
                client.get(args.query).raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 29:
                    raise
                time.sleep(1)
        for path in exports:
            data = json.loads(path.read_text(encoding="utf-8"))
            spans = data["resourceSpans"][0]["scopeSpans"][0]["spans"]
            trace_id = spans[0]["traceId"]
            protobuf = path.stem.endswith("-fork")
            source = path.with_suffix(".otlp-protobuf") if protobuf else path
            response = client.post(
                args.collector,
                content=source.read_bytes(),
                headers={
                    "Content-Type": "application/x-protobuf" if protobuf else "application/json"
                },
            )
            response.raise_for_status()
            # A successful HTTP response can still report rejected spans.
            if not protobuf:
                partial = response.json().get("partialSuccess", {})
                assert int(partial.get("rejectedSpans", 0)) == 0, partial
            else:
                from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
                    ExportTraceServiceResponse,
                )

                accepted = ExportTraceServiceResponse.FromString(response.content)
                assert accepted.partial_success.rejected_spans == 0
            expected = {span["spanId"]: span for span in spans}
            stored = []
            for _ in range(30):
                result = client.get(f"{args.query}/api/traces/{trace_id}")
                if result.status_code == 200:
                    traces = result.json().get("data") or []
                    if traces:
                        stored = traces[0]["spans"]
                        if len(stored) == len(expected):
                            break
                time.sleep(1)
            assert len(stored) == len(expected), f"Missing spans for {trace_id}"
            for span in stored:
                original = expected[span["spanID"]]
                assert span["operationName"] == original["name"]
                tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}
                attributes = {row["key"]: row["value"] for row in original["attributes"]}
                for key in (
                    "rewind.chain_hash",
                    "rewind.counterfactual",
                    "rewind.parent_fingerprint",
                ):
                    assert tags[key] == attributes[key]["stringValue"], (key, tags)
            reports.append(
                {
                    "file": source.name,
                    "wire_format": "protobuf" if protobuf else "json",
                    "trace_id": trace_id,
                    "stored_spans": len(stored),
                    "hashes_and_quarantine_preserved": True,
                }
            )
    if args.screenshot:
        from playwright.sync_api import sync_playwright

        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(f"{args.query}/trace/{reports[0]['trace_id']}")
            page.get_by_text("month3.quote", exact=False).first.wait_for(timeout=30000)
            page.screenshot(path=str(args.screenshot), full_page=True)
            browser.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
