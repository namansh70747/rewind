"""Record a controlled NVIDIA NIM response and verify it offline.

Set NVIDIA_API_KEY in the environment before recording; replay needs no credential.
Recordings contain prompt/response data, so review them before sharing.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from flightrecorder.interceptors.transport import RecordingTransport
from flightrecorder.portable import export_run, import_run
from flightrecorder.replay import record, verify

if TYPE_CHECKING:
    from flightrecorder.boundary import Session

MODEL = "nvidia/nemotron-3-super-120b-a12b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
PROMPT = "Explain deterministic record and replay in two brief sentences."


def make_run(model: str, api_key: str):
    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        with httpx.Client(transport=RecordingTransport(session, inner), timeout=120) as client:
            response = client.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "max_tokens": 256,
                    "stream": False,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Provider returned no text content")
            return content

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["record", "verify"])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--output", type=Path, default=Path(".rewind/nvidia/run.json"))
    parser.add_argument("--replays", type=int, default=50)
    args = parser.parse_args()
    if args.replays < 1 or args.replays > 1000:
        parser.error("--replays must be between 1 and 1000")
    if args.mode == "record":
        key = os.environ.get("NVIDIA_API_KEY", "")
        if not key:
            parser.error("Set NVIDIA_API_KEY locally before recording")
        if args.output.exists():
            parser.error("Choose a new output path to preserve existing evidence")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with httpx.HTTPTransport() as transport:
            cassette = record(
                make_run(args.model, key), transport, provider="nvidia", model=args.model
            )
        export_run(cassette, args.output)
        print(f"Recorded NVIDIA run to {args.output}; review before sharing.")
    else:
        cassette = import_run(args.output)
        if cassette.provider != "nvidia":
            parser.error("Recording is not labelled as NVIDIA")
        result = verify(cassette, make_run(cassette.model, ""), args.replays)
        print(json.dumps(asdict(result), indent=2))
        raise SystemExit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
