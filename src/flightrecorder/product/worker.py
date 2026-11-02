"""Run a trusted script capture or offline verification in a separate process."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from flightrecorder.redaction import RedactionRules, redaction_rules
from flightrecorder.scripts import record_script, verify_script
from flightrecorder.store import RunStore


def main() -> None:
    request = json.load(sys.stdin)
    store = RunStore(request["db"])
    try:
        source = Path(request["source"])
        keys = tuple(
            value
            for name in (
                "NVIDIA_API_KEY",
                "GEMINI_API_KEY",
                "GROQ_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
            if (value := os.environ.get(name))
        )
        with redaction_rules(RedactionRules(literals=keys)):
            if request["action"] == "capture":
                cassette = record_script(source)
                cassette.metadata["product_source"] = str(source)
                known_examples = {
                    "product_groq_agent.py": ("Groq", "openai/gpt-oss-20b"),
                    "product_groq_stream.py": ("Groq", "openai/gpt-oss-20b"),
                    "product_nvidia_agent.py": ("NVIDIA", "nvidia/nemotron-3-super-120b-a12b"),
                    "product_gemini_agent.py": ("Gemini", "gemini-2.5-flash"),
                }
                if (
                    source.resolve().parent == (Path.cwd() / "examples").resolve()
                    and source.name in known_examples
                ):
                    cassette.metadata["product_provider"], cassette.metadata["product_model"] = (
                        known_examples[source.name]
                    )
                if source.resolve() == (Path.cwd() / "examples/http_agent.py").resolve():
                    cassette.metadata["simulated"] = True
                run_id = store.save(cassette)
                result = {"run_id": run_id, "boundaries": len(cassette.boundaries)}
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
