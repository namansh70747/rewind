"""Trusted Python script recording with source drift checks and stdout verification."""

from __future__ import annotations

import hashlib
import io
import runpy
import sys
from contextlib import redirect_stdout
from typing import TYPE_CHECKING, Any

from .boundary import Cassette, Divergence
from .capture import capture, replay_run
from .redaction import redact_text
from .replay import VerifyResult

if TYPE_CHECKING:
    from pathlib import Path


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute(path: Path) -> str:
    output = io.StringIO()
    original_argv, original_path = sys.argv[:], sys.path[:]
    try:
        sys.argv = [str(path)]
        sys.path.insert(0, str(path.resolve().parent))
        with redirect_stdout(output):
            runpy.run_path(str(path), run_name="__main__")
        return redact_text(output.getvalue())
    finally:
        sys.argv = original_argv
        sys.path = original_path


def record_script(path: Path, *, concurrent: bool = False, sources: bool = False) -> Cassette:
    """Executes trusted code. Only httpx clients created inside capture are intercepted."""
    digest = source_hash(path)
    with capture(provider="script", model=path.name, concurrent=concurrent, sources=sources) as cap:
        output = _execute(path)
    assert cap.cassette is not None
    cap.cassette.final_output = output
    cap.cassette.metadata = {
        **cap.cassette.metadata,
        "source_sha256": digest,
        "source_name": path.name,
        "capture_scope": "httpx + decorated tools + optional sources + redacted stdout",
    }
    return cap.cassette


def verify_script(cassette: Cassette, path: Path, n: int = 10) -> VerifyResult:
    if n < 1:
        raise ValueError("number of replays must be at least 1")
    actual = source_hash(path)
    expected = cassette.metadata.get("source_sha256")
    if cassette.provider != "script" or actual != expected:
        raise ValueError(
            f"script source differs from the recording: recorded SHA {expected}, "
            f"current SHA {actual}; restore the original file"
        )
    outputs: set[str] = set()
    hashes: set[str] = set()
    for index in range(n):

        def run() -> Any:
            output = _execute(path)
            outputs.add(output)
            if output != cassette.final_output:
                raise Divergence(len(cassette.boundaries), "script stdout differs from recording")

        try:
            hashes.add(replay_run(cassette, run))
        except RuntimeError as exc:
            return VerifyResult(False, index + 1, len(outputs), len(hashes), str(exc))
        except Divergence as exc:
            return VerifyResult(False, index + 1, len(outputs), len(hashes), str(exc))
    passed = hashes == {cassette.fingerprint} and outputs == {cassette.final_output}
    return VerifyResult(
        passed,
        n,
        len(outputs),
        len(hashes),
        "HTTP boundaries and redacted stdout match; source hash checked",
    )


def fork_script(
    parent: Cassette, path: Path, *, at: int, value: Any, mocks: dict[tuple[str, str], Any]
) -> Cassette:
    """Replay a trusted recorded script with one intervention and JSON-value mocks."""
    from contextlib import nullcontext
    from functools import partial

    from .boundary import Session
    from .capture import _patched
    from .fork import fork_run
    from .replay import Run
    from .sources import deterministic_sources

    actual = source_hash(path)
    expected = parent.metadata.get("source_sha256")
    if actual != expected:
        raise ValueError(
            f"script source differs from recording: recorded SHA {expected}, current SHA {actual}"
        )
    if parent.metadata.get("concurrent"):
        raise ValueError("concurrent forks are not supported; serialize this scenario")

    def execute(session: Session, transport: Any) -> str:
        with (
            _patched(session),
            deterministic_sources(session) if parent.metadata.get("sources") else nullcontext(),
        ):
            return _execute(path)

    run: Run = execute
    return fork_run(
        parent,
        run,
        at=at,
        value=value,
        mocks={
            key: partial(lambda result, request: result, result) for key, result in mocks.items()
        },
    )
