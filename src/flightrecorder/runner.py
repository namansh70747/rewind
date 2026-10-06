"""In-process runner for ``fr record -- python agent.py``.

Runs an unmodified agent script under :func:`flightrecorder.capture.capture` so the
``httpx`` monkeypatch applies (a subprocess would not see the patch). A true
``sitecustomize`` boot-shim for out-of-process capture is a later phase.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """Strip a leading ``python`` / ``python3`` / ``py`` interpreter token if present."""
    args = list(argv)
    if not args:
        raise ValueError("missing agent script — use: fr record -- python your_agent.py [args]")
    head = Path(args[0]).name.lower()
    if head in {"python", "python3", "python.exe", "python3.exe", "py", "py.exe"}:
        args = args[1:]
    if not args:
        raise ValueError("missing agent script — use: fr record -- python your_agent.py [args]")
    return args


def make_runner(argv: Sequence[str]) -> Callable[[], None]:
    """Return a zero-arg callable that executes ``argv`` as ``python script.py …``."""
    args = normalize_argv(argv)
    script = Path(args[0]).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"agent script not found: {script}")
    script_args = args[1:]

    def run() -> None:
        old_argv = sys.argv
        sys.argv = [str(script), *script_args]
        try:
            runpy.run_path(str(script), run_name="__main__")
        finally:
            sys.argv = old_argv

    return run
