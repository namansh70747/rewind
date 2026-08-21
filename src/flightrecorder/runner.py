"""Run an arbitrary Python agent in-process so its ``httpx`` calls cross the capture boundary.

``fr record -- python agent.py <args>`` records an *unmodified* agent: nothing in the agent
imports or knows about Rewind. The agent runs in this same interpreter (via :mod:`runpy`)
rather than a subprocess, so the ``httpx`` patch installed by :func:`flightrecorder.capture`
(record) and :func:`flightrecorder.capture.replay_run` (replay) sees every call it makes.

``sys.argv`` is swapped for the agent and restored afterwards so the host CLI is unaffected,
and a clean ``SystemExit(0)`` the agent may raise on completion is swallowed (a non-zero exit
is a real failure and propagates). Only Python scripts are supported for now; a general
subprocess wrapper (via a ``sitecustomize`` boot shim) is a later phase.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def parse_command(argv: list[str]) -> tuple[str, list[str]]:
    """Resolve ``[python, script.py, args…]`` (or ``[script.py, args…]``) to ``(script, argv)``.

    The returned ``argv`` is what the agent sees as ``sys.argv`` — script first, then its args.
    """
    if not argv:
        raise ValueError("no command given to record")
    tokens = list(argv)
    if Path(tokens[0]).stem in {"python", "python3"}:
        tokens = tokens[1:]
    if not tokens or not tokens[0].endswith(".py"):
        raise ValueError(
            f"can only record a Python script for now (got {argv!r}); "
            "use: fr record -- python your_agent.py [args]"
        )
    if not Path(tokens[0]).exists():
        raise ValueError(f"agent script not found: {tokens[0]}")
    return tokens[0], tokens


def make_runner(argv: list[str]) -> Callable[[], None]:
    """Return a zero-arg thunk that runs the agent once with ``argv``, in this interpreter."""
    script, script_argv = parse_command(argv)

    def run() -> None:
        saved_argv = sys.argv
        sys.argv = script_argv
        try:
            runpy.run_path(script, run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
        finally:
            sys.argv = saved_argv

    return run


def encode_command(argv: list[str]) -> str:
    """Serialize an agent's argv for storage in the cassette."""
    return json.dumps(argv)


def decode_command(command: str) -> list[str]:
    """Recover an agent's argv from a cassette so ``verify`` can re-run it."""
    return list(json.loads(command))
