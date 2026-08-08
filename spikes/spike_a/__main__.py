"""CLI for the Spike A go/no-go.

    # Live go/no-go against Claude (needs ANTHROPIC_API_KEY in env or .env):
    python -m spikes.spike_a record --provider anthropic --n 50

    # ...or OpenAI (OPENAI_API_KEY):
    python -m spikes.spike_a record --provider openai --n 50

    # Offline replay of a saved cassette (no key needed):
    python -m spikes.spike_a verify spikes/spike_a/last_run.cassette.json --n 50

The API key is read from the environment or a local, git-ignored ``.env`` file.
PASS = every replay is byte-identical to the recording, with zero API calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from .agent import PROVIDERS, make_run, record, verify
from .engine import Cassette

DEFAULT_CASSETTE = Path("spikes/spike_a/last_run.cassette.json")


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny, dependency-free .env loader: `KEY=value` lines, existing env wins."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _cmd_record(args: argparse.Namespace) -> int:
    provider = PROVIDERS[args.provider]
    api_key = os.environ.get(provider.key_env, "")
    if not api_key:
        print(
            f"error: set {provider.key_env} (in your environment or a .env file) to record "
            f"a live {provider.name} run. Replay itself needs no key."
        )
        return 2
    model = args.model or provider.default_model
    run = make_run(provider, args.model, api_key)
    print(f"recording one live {provider.name} run ({model}) ...")
    cassette = record(run, httpx.HTTPTransport())
    Path(args.out).write_text(cassette.to_json(), encoding="utf-8")
    print(f"recorded {len(cassette.boundaries)} boundaries -> {args.out}")
    print(f"fingerprint : {cassette.fingerprint}")
    print(f"output      : {cassette.final_output}")
    print(f"\nreplaying {args.n}x offline (network kill-switch on) ...")
    result = verify(cassette, make_run(provider, args.model, api_key), n=args.n)
    print(result)
    return 0 if result.passed else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    cassette = Cassette.from_json(Path(args.cassette).read_text(encoding="utf-8"))
    provider = PROVIDERS[args.provider]
    result = verify(cassette, make_run(provider, args.model, "replay-needs-no-key"), n=args.n)
    print(result)
    return 0 if result.passed else 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="openai")
    parser.add_argument("--model", default=None, help="override the provider's default model")
    parser.add_argument("--n", type=int, default=50, help="number of replays to verify")


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="spikes.spike_a", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="record one live run, then verify it offline")
    _add_common(p_rec)
    p_rec.add_argument("--out", default=str(DEFAULT_CASSETTE))
    p_rec.set_defaults(func=_cmd_record)

    p_ver = sub.add_parser("verify", help="replay an existing cassette offline")
    _add_common(p_ver)
    p_ver.add_argument("cassette", nargs="?", default=str(DEFAULT_CASSETTE))
    p_ver.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
