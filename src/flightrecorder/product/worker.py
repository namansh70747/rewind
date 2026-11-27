"""Run a trusted script capture or offline verification in a separate process."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from flightrecorder.providers import configured_secrets
from flightrecorder.redaction import RedactionRules, redaction_rules
from flightrecorder.scripts import record_script, verify_script
from flightrecorder.store import RunStore


def main() -> None:
    request = json.load(sys.stdin.buffer)
    store = RunStore(request["db"])
    try:
        source = Path(request["source"])
        with redaction_rules(RedactionRules(literals=configured_secrets())):
            if request["action"] == "capture":
                cassette = record_script(source)
                cassette.metadata["product_source"] = str(source)
                if source.resolve() == (Path.cwd() / "examples/http_agent.py").resolve():
                    cassette.metadata["simulated"] = True
                run_id = store.save(cassette)
                result = {"run_id": run_id, "boundaries": len(cassette.boundaries)}
                if "script_error" in cassette.metadata:
                    result["script_error"] = cassette.metadata["script_error"]
            else:
                result = asdict(
                    verify_script(store.load(request["run_id"]), source, request["replays"])
                )
        print(json.dumps({"ok": True, "result": result}))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: Check the script and provider configuration.",
                }
            )
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
