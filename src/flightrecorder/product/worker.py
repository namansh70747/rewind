"""Run a trusted script capture or offline verification in a separate process."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from flightrecorder.boundary import Divergence
from flightrecorder.offline import NetworkBlocked
from flightrecorder.redaction import RedactionRules, redact_text, redaction_rules
from flightrecorder.scripts import (
    CapturePersistenceError,
    fork_script,
    record_script_to_store,
    verify_script,
)
from flightrecorder.store import RunStore


def main() -> None:
    request = json.load(sys.stdin)
    store = RunStore(request["db"])
    rules = RedactionRules().with_provider_keys()
    try:
        source = Path(request["source"])
        with redaction_rules(rules):
            if request["action"] == "capture":
                metadata: dict[str, Any] = {"product_source": str(source)}
                if source.resolve() == (Path.cwd() / "examples/http_agent.py").resolve():
                    metadata["simulated"] = True
                run_id, cassette = record_script_to_store(store, source, metadata=metadata)
                result = {
                    "run_id": run_id,
                    "boundaries": len(cassette.boundaries),
                    "sample": bool(cassette.metadata.get("simulated")),
                    "terminal_outcome": cassette.metadata["terminal_outcome"],
                }
            elif request["action"] == "fork":
                intervention = request["intervention"]
                child = fork_script(
                    store.load_validated(request["run_id"]),
                    source,
                    at=intervention["at"],
                    value=intervention["value"],
                    mocks={},
                )
                child.metadata["parent_run"] = request["run_id"]
                result = {
                    "run_id": store.save(child),
                    "boundaries": len(child.boundaries),
                    "sample": bool(child.metadata.get("simulated")),
                }
            else:
                result = asdict(
                    verify_script(store.load(request["run_id"]), source, request["replays"])
                )
        print(json.dumps({"ok": True, "result": result}))
    except (Divergence, NetworkBlocked, ValueError, CapturePersistenceError) as exc:
        with redaction_rules(rules):
            print(json.dumps({"ok": False, "error": redact_text(str(exc))}))
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
