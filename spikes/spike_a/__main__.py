"""CLI for the Spike A go/no-go.

    # Live go/no-go (needs OPENAI_API_KEY): record one real run, then replay it 50x.
    python -m spikes.spike_a record --n 50

    # Offline: replay an existing cassette and re-check faithfulness.
    python -m spikes.spike_a verify spikes/spike_a/last_run.cassette.json --n 50

PASS = 50/50 replays are byte-identical to the recording with zero API calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from .agent import make_run, record, verify
from .engine import Cassette

DEFAULT_CASSETTE = Path("spikes/spike_a/last_run.cassette.json")


def _cmd_record(args: argparse.Namespace) -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("error: set OPENAI_API_KEY to record a live run (replay itself needs no key).")
        return 2
    run = make_run(args.base_url, api_key)
    print("recording one live agent run ...")
    cassette = record(run, httpx.HTTPTransport())
    path = Path(args.out)
    path.write_text(cassette.to_json(), encoding="utf-8")
    print(f"recorded {len(cassette.boundaries)} boundaries → {path}")
    print(f"run fingerprint: {cassette.fingerprint}")
    print(f"\nreplaying {args.n}x offline (network kill-switch on) ...")
    result = verify(cassette, make_run(args.base_url, api_key), n=args.n)
    print(result)
    return 0 if result.passed else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    cassette = Cassette.from_json(Path(args.cassette).read_text(encoding="utf-8"))
    result = verify(cassette, make_run(args.base_url, "replay-needs-no-key"), n=args.n)
    print(result)
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spikes.spike_a", description=__doc__)
    parser.add_argument("--base-url", default="https://api.openai.com")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="record one live run, then verify")
    p_rec.add_argument("--n", type=int, default=50)
    p_rec.add_argument("--out", default=str(DEFAULT_CASSETTE))
    p_rec.set_defaults(func=_cmd_record)

    p_ver = sub.add_parser("verify", help="replay an existing cassette offline")
    p_ver.add_argument("cassette", default=str(DEFAULT_CASSETTE), nargs="?")
    p_ver.add_argument("--n", type=int, default=50)
    p_ver.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
