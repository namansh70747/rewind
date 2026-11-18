"""Record a controlled NVIDIA or Gemini corpus, then verify without extra API calls.

Requires NVIDIA_API_KEY or GEMINI_API_KEY locally. Makes three model calls per
recording. This is not a 672-tool fleet. OpenAI and Anthropic are out of course
scope (ADR-0015).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from flightrecorder.evaluation import evaluate_manifest
from flightrecorder.portable import export_run
from flightrecorder.providers import GEMINI, NVIDIA, PROVIDERS
from flightrecorder.redaction import redact_text
from flightrecorder.scripts import record_script

COURSE_PROVIDERS = {"nvidia": NVIDIA, "gemini": GEMINI}


def agent_source(provider: str, model: str, case: int) -> str:
    if provider not in COURSE_PROVIDERS:
        raise ValueError("course corpus uses nvidia or gemini only")
    price = 420 if case % 2 else 720
    return f"""import json
import os

import httpx

from flightrecorder import tool
from flightrecorder.providers import PROVIDERS

provider = PROVIDERS[{provider!r}]
key = os.environ.get(provider.key_env, "")


@tool(name="normalize_case", mutating=False)
def normalize_case(value):
    return {{"case": value, "budget": 500}}


@tool(name="check_budget", mutating=False)
def check_budget(price):
    return {{"price": price, "within_budget": price <= 500}}


case = normalize_case({case})
outputs = []
with httpx.Client(timeout=120, trust_env=False) as client:
    for step in range(3):
        prompt = "Controlled Rewind qualification. Reply briefly with OK. {case} step " + str(step)
        response = client.post(
            provider.url,
            headers=provider.headers(key),
            json=provider.body({model!r}, [{{"role": "user", "content": prompt}}]),
        )
        response.raise_for_status()
        outputs.append(provider.extract(response.json()))
    result = check_budget({price})
    print(json.dumps({{"outputs": outputs, "budget": result}}, sort_keys=True))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(COURSE_PROVIDERS))
    parser.add_argument("model", nargs="?", default=None, help="defaults to the course provider model")
    parser.add_argument("--runs", type=int, default=10, choices=range(2, 16))
    parser.add_argument("--replays", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path(".rewind/provider-corpus"))
    args = parser.parse_args()
    if not 50 <= args.replays <= 1000:
        parser.error("qualification requires between 50 and 1000 offline replays")
    spec = PROVIDERS[args.provider]
    model = args.model or spec.default_model
    if not os.environ.get(spec.key_env):
        parser.error(f"configure {spec.key_env} locally; never place credentials in source or chat")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("choose an empty output directory to preserve earlier evidence")
    args.output.mkdir(parents=True, exist_ok=True)
    fixtures = []
    failures = []
    for index in range(args.runs):
        script = args.output / f"agent-{index:02}.py"
        script.write_text(agent_source(args.provider, model, index), encoding="utf-8")
        try:
            recording = record_script(script)
            recording.metadata["qualification_origin"] = "controlled-live-provider"
            recording.metadata["external_provider"] = args.provider
            recording.metadata["external_model"] = model
            destination = args.output / f"run-{index:02}.json"
            export_run(recording, destination)
            fixtures.append({"script": script.name, "recording": destination.name})
            print(f"Recorded {index + 1}/{args.runs}: {len(recording.boundaries)} boundaries")
        except Exception as exc:
            failures.append({"case": index, "error": redact_text(str(exc))})
            break
    manifest = args.output / "fixtures.json"
    manifest.write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
    evaluation = evaluate_manifest(manifest, args.replays) if fixtures else {"passed": False}
    report = {
        "origin": "controlled NVIDIA/Gemini prompts, not author fleet or billed OpenAI/Anthropic",
        "provider": args.provider,
        "model": model,
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
