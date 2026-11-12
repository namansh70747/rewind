"""Load exported JSON unchanged through Perfetto's official trace processor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from perfetto.trace_processor import TraceProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".rewind/perfetto-report.json"))
    args = parser.parse_args()
    reports = []
    for trace in args.traces:
        original = trace.read_bytes()
        events = json.loads(original)["traceEvents"]
        with TraceProcessor(trace=str(trace)) as processor:
            rows = list(processor.query("select name, count(*) as n from slice group by name"))
            expected = {}
            for event in events:
                expected[event["name"]] = expected.get(event["name"], 0) + 1
            assert {row.name: row.n for row in rows} == expected
            errors = list(
                processor.query(
                    "select name, value from stats where severity = 'error' and value > 0"
                )
            )
            assert not errors, [(row.name, row.value) for row in errors]
        assert trace.read_bytes() == original
        reports.append(
            {
                "file": trace.name,
                "sha256": hashlib.sha256(original).hexdigest(),
                "slices": len(events),
                "loaded_unchanged": True,
                "parser_errors": 0,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
