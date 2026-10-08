"""Record a controlled live-provider corpus, then verify without additional API calls.

Requires your own configured provider credentials and explicitly selected model.
This makes three billable model calls per recording. It is not real fleet evidence.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

from flightrecorder.evaluation import evaluate_manifest
from flightrecorder.portable import export_run
from flightrecorder.redaction import redact_text
from flightrecorder.scripts import record_script


def agent_source(provider: str, model: str, case: int) -> str:
    if provider == "openai":
        imports = "from openai import OpenAI\nclient = OpenAI(max_retries=0)"
        call = (
            f"client.chat.completions.create(model={model!r}, max_tokens=32, "
            "messages=[{'role': 'user', 'content': prompt}]).choices[0].message.content"
        )
    else:
        imports = "from anthropic import Anthropic\nclient = Anthropic(max_retries=0)"
        call = (
            f"client.messages.create(model={model!r}, max_tokens=32, "
            "messages=[{'role': 'user', 'content': prompt}]).model_dump(mode='json')"
        )
    return f"""import json
from flightrecorder import tool
{imports}

@tool(name="normalize_case", mutating=False)
def normalize_case(value):
    return {{"case": value, "budget": 500}}

@tool(name="check_budget", mutating=False)
def check_budget(price):
    return {{"price": price, "within_budget": price <= 500}}

case = normalize_case({case})
outputs = []
try:
    for step in range(3):
        prompt = "Controlled Rewind qualification. Reply briefly with OK. " + str(case) + " step " + str(step)
        outputs.append({call})
    result = check_budget({420 if case % 2 else 720})
    print(json.dumps({{"outputs": outputs, "budget": result}}, sort_keys=True))
finally:
    client.close()
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=["openai", "anthropic"])
    parser.add_argument("model", help="a model available to your account")
    parser.add_argument("--runs", type=int, default=10, choices=range(10, 16))
    parser.add_argument("--replays", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path(".rewind/provider-corpus"))
    args = parser.parse_args()
    if not 50 <= args.replays <= 1000:
        parser.error("qualification requires between 50 and 1000 offline replays")
    key = "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key):
        parser.error(f"configure {key} locally; never place credentials in source or chat")
    if importlib.util.find_spec(args.provider) is None:
        parser.error("install the integrations extra first")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("choose an empty output directory to preserve earlier evidence")
    args.output.mkdir(parents=True, exist_ok=True)
    fixtures = []
    failures = []
    for index in range(args.runs):
        script = args.output / f"agent-{index:02}.py"
        script.write_text(agent_source(args.provider, args.model, index), encoding="utf-8")
        try:
            recording = record_script(script)
            recording.metadata["qualification_origin"] = "controlled-live-provider"
            recording.metadata["external_provider"] = args.provider
            recording.metadata["external_model"] = args.model
            destination = args.output / f"run-{index:02}.json"
            export_run(recording, destination)
            fixtures.append({"script": script.name, "recording": destination.name})
            print(f"Recorded {index + 1}/{args.runs}: {len(recording.boundaries)} boundaries")
        except Exception as exc:
            failures.append({"case": index, "error": redact_text(str(exc))})
            # Avoid repeating a billing/authentication/provider failure across the corpus.
            break
    manifest = args.output / "fixtures.json"
    manifest.write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
    evaluation = evaluate_manifest(manifest, args.replays) if fixtures else {"passed": False}
    report = {
        "origin": "controlled live-provider prompts, not author fleet or real failing-agent demo",
        "provider": args.provider,
        "model": args.model,
        "requested_recordings": args.runs,
        "completed_recordings": len(fixtures),
        "capture_failures": failures,
        "evaluation": evaluation,
        "passed": not failures and len(fixtures) == args.runs and evaluation["passed"],
        "human_redaction_review": "required before sharing",
    }
    (args.output / "qualification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {args.output / 'qualification.json'}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
