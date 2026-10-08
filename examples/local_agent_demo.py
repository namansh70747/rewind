"""Actual local-model capture and controlled fork, with explicitly simulated tools.

Record against an existing Ollama model, stop Ollama, then verify offline:
  python examples/local_agent_demo.py record YOUR_MODEL
  python examples/local_agent_demo.py verify
No model download, cloud service or real reservation is performed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from flightrecorder.dashboard import render_dashboard
from flightrecorder.diagnosis import hash_bisect
from flightrecorder.fork import fork_run
from flightrecorder.interceptors.transport import RecordingTransport
from flightrecorder.policy import PolicyForkSession, SideEffectPolicy, fork_with_policy
from flightrecorder.portable import export_run, import_run
from flightrecorder.replay import record, verify
from flightrecorder.scripts import source_hash

if TYPE_CHECKING:
    from flightrecorder.boundary import Cassette, Session
    from flightrecorder.replay import Run


def reservation(request: Any) -> dict[str, Any]:
    status = (
        "over_budget"
        if request["price"] > 500
        else ("confirmed" if request["action"] == "book" else "declined")
    )
    return {"status": status, "price": request["price"], "simulated": True}


def make_run(model: str, endpoint: str, quote: int = 720) -> Run:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("this demo requires a local Ollama HTTP endpoint")

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        task = session.mediate("input", "travel_request", None, lambda: {"budget": 500})
        fare = session.mediate(
            "tool",
            "price_lookup",
            {"destination": "Jaipur"},
            lambda: {"price": quote, "source": "simulated-cache"},
        )
        # Only the explicitly allowlisted fork may instantiate a fresh live transport.
        if isinstance(session, PolicyForkSession) and session.policy.permits(
            "http", "/api/generate"
        ):
            inner = httpx.HTTPTransport()
        with httpx.Client(
            transport=RecordingTransport(session, inner), timeout=120, trust_env=False
        ) as client:
            response = client.post(
                endpoint.rstrip("/") + "/api/generate",
                json={
                    "model": model,
                    "stream": False,
                    "prompt": (
                        f"Budget is {task['budget']}. Price is {fare['price']}. "
                        "Choose book if price <= budget, otherwise reject. Return JSON only."
                    ),
                    "format": {
                        "type": "object",
                        "properties": {"action": {"type": "string", "enum": ["book", "reject"]}},
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                    "options": {"temperature": 0, "seed": 42, "num_predict": 64},
                },
            )
            response.raise_for_status()
            decision = json.loads(response.json()["response"])
        if not isinstance(decision, dict) or decision.get("action") not in {"book", "reject"}:
            raise ValueError("model returned an invalid decision")
        state = {"price": fare["price"], "budget": task["budget"], "action": decision["action"]}
        session.mediate("state", "agent_state", state, lambda: state)
        result = session.mediate("tool", "reserve_trip", state, lambda: reservation(state))
        return json.dumps(result, sort_keys=True)

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["record", "verify"])
    parser.add_argument("model", nargs="?")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, default=Path(".rewind/local-agent"))
    args = parser.parse_args()
    labels = {
        "failed": "Failed · actual local model",
        "fresh": "Fresh · actual local model",
        "fork": "Fork · live local model, mocked tools",
        "decision_fork": "Recovery · injected model decision, mocked tools",
    }
    if args.mode == "record":
        if not args.model:
            parser.error("record requires an already-installed local model")
        if args.output.exists() and any(args.output.iterdir()):
            parser.error("choose an empty output directory to preserve earlier evidence")
        args.output.mkdir(parents=True, exist_ok=True)
        runs: dict[str, Cassette] = {}
        for name, price in [("failed", 720), ("fresh", 420)]:
            with httpx.HTTPTransport() as inner:
                cassette = record(
                    make_run(args.model, args.endpoint, price),
                    inner,
                    provider="local-ollama",
                    model=args.model,
                )
            cassette.metadata.update(
                {
                    "simulated_tools": True,
                    "model_inference": "actual local model",
                    "endpoint": args.endpoint,
                    "source_sha256": source_hash(Path(__file__)),
                }
            )
            runs[name] = cassette
            export_run(cassette, args.output / f"{name}.json")
        runs["fork"] = fork_with_policy(
            runs["failed"],
            make_run(args.model, args.endpoint),
            at=1,
            value={"price": 420, "source": "simulated-cache"},
            mocks={
                ("state", "agent_state"): lambda request: request,
                ("tool", "reserve_trip"): reservation,
            },
            policy=SideEffectPolicy(live_allowlist=frozenset({("http", "/api/generate")})),
        )
        export_run(runs["fork"], args.output / "fork.json")
        # Preserve a poor model decision rather than silently changing the model
        # output. Explore an explicit answer intervention on the affordable run.
        runs["decision_fork"] = fork_run(
            runs["fresh"],
            make_run(args.model, args.endpoint),
            at=2,
            value={
                "status": 200,
                "content_type": "application/json",
                "body": {
                    "json": {
                        "model": args.model,
                        "response": '{"action":"book"}',
                        "done": True,
                        "counterfactual": True,
                    }
                },
            },
            mocks={
                ("state", "agent_state"): lambda request: request,
                ("tool", "reserve_trip"): reservation,
            },
        )
        runs["decision_fork"].metadata["model_inference"] = (
            "injected counterfactual decision, not live inference"
        )
        export_run(runs["decision_fork"], args.output / "decision_fork.json")
        print("Recorded two actual model runs and one explicitly allowlisted local-model fork.")
        print("Also saved a separately labeled model-decision intervention with mocked tools.")
        print("Stop Ollama, then run this example with verify and the same --output path.")
        return

    runs = {name: import_run(args.output / f"{name}.json") for name in labels}
    checks = {}
    for name, cassette in runs.items():
        if cassette.metadata.get("source_sha256") != source_hash(Path(__file__)):
            raise ValueError("example source differs from the recorded version")
        checks[labels[name]] = asdict(
            verify(cassette, make_run(cassette.model, cassette.metadata["endpoint"]), 50)
        )
    outcomes = {
        name: json.loads(cassette.final_output)["status"] for name, cassette in runs.items()
    }
    passed = (
        all(row["passed"] for row in checks.values())
        and outcomes["failed"] == "over_budget"
        and outcomes["decision_fork"] == "confirmed"
    )
    report = {
        "passed": passed,
        "verification": checks,
        "outcomes": outcomes,
        "divergence": hash_bisect(runs["failed"], runs["fresh"]),
        "decision_intervention_at": hash_bisect(runs["fresh"], runs["decision_fork"]),
        "live_quote_fork_recovered": outcomes["fork"] == "confirmed",
        "interpretation": "Quote-only live continuation may fail; injected decision is a labeled what-if, not a model accuracy fix.",
        "scope": "Actual local LLM; controlled scenario and simulated tools, not real fleet acceptance.",
    }
    (args.output / "qualification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_dashboard(
        {labels[name]: c for name, c in runs.items()}, args.output / "demo.html", checks
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
