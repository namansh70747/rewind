"""Execute a single job received over the private supervisor's process pipe."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from flightrecorder.boundary import canon
from flightrecorder.portable import envelope, parse_envelope
from flightrecorder.providers import configured_secrets
from flightrecorder.redaction import RedactionRules, redaction_rules
from flightrecorder.scripts import record_script, source_hash, verify_script

MAX_RESULT = 1_500_000


def main() -> int:
    try:
        request = json.load(sys.stdin.buffer)
        source = Path(request["source"])
        if source_hash(source) != request["source_digest"]:
            print('{"error":"Approved source changed. Restart with the reviewed demo scripts."}')
            return 1
        literals = (*configured_secrets(), str(source), str(source.parent))
        with redaction_rules(RedactionRules(literals=literals)):
            if request["action"] == "capture":
                result = {"bundle": envelope(record_script(source))}
            elif request["action"] == "verify":
                cassette = parse_envelope(request["bundle"])
                cassette.metadata["source_sha256"] = request["source_digest"]
                result = {
                    "verification": asdict(verify_script(cassette, source, request["replays"]))
                }
            else:
                raise ValueError("Unsupported worker action")
        payload = canon(result)
        if len(payload) > MAX_RESULT:
            print('{"error":"Recording exceeds the demo limit. Capture this run locally."}')
            return 1
        sys.stdout.buffer.write(payload)
        return 0
    except Exception:
        print('{"error":"Demo execution failed. Check the approved script and provider setup."}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
