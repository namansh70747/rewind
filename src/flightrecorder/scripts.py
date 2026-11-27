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
from .offline import NetworkBlocked
from .provenance import check_source, provenance
from .providers import hosted_model
from .redaction import redact_text
from .replay import VerifyResult

if TYPE_CHECKING:
    from pathlib import Path

    from .policy import SideEffectPolicy


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute(path: Path) -> tuple[str, str | None]:
    output = io.StringIO()
    original_argv, original_path = sys.argv[:], sys.path[:]
    try:
        sys.argv = [str(path)]
        sys.path.insert(0, str(path.resolve().parent))
        with redirect_stdout(output):
            try:
                runpy.run_path(str(path), run_name="__main__")
            except (Divergence, NetworkBlocked):
                raise
            except (Exception, SystemExit) as exc:
                if isinstance(exc, SystemExit) and (
                    exc.code is None or (isinstance(exc.code, int) and exc.code == 0)
                ):
                    return redact_text(output.getvalue()), None
                kind = type(exc)
                failure = redact_text(f"{kind.__module__}.{kind.__qualname__}: {exc}")
                return redact_text(output.getvalue()), failure
        return redact_text(output.getvalue()), None
    finally:
        sys.argv = original_argv
        sys.path = original_path


def record_script(path: Path, *, concurrent: bool = False, sources: bool = False) -> Cassette:
    """Executes trusted code. Only httpx clients created inside capture are intercepted."""
    digest = source_hash(path)
    with capture(provider="script", model=path.name, concurrent=concurrent, sources=sources) as cap:
        output, failure = _execute(path)
    assert cap.cassette is not None
    cap.cassette.final_output = output
    cap.cassette.metadata = {
        **cap.cassette.metadata,
        **provenance(path),
        "source_sha256": digest,
        "source_name": path.name,
        "capture_scope": "httpx + decorated tools + optional sources + redacted stdout",
    }
    if identity := hosted_model(cap.cassette):
        cap.cassette.metadata["product_provider"], cap.cassette.metadata["product_model"] = identity
    if failure is not None:
        cap.cassette.metadata["script_error"] = failure
    return cap.cassette


def verify_script(cassette: Cassette, path: Path, n: int = 10) -> VerifyResult:
    if n < 1:
        raise ValueError("number of replays must be at least 1")
    if cassette.provider != "script":
        raise ValueError("recording is not a script")
    if cassette.metadata.get("counterfactual"):
        raise ValueError("What-if forks cannot be verified as original recordings")
    check_source(cassette.metadata, path)
    outputs: set[str] = set()
    hashes: set[str] = set()
    for index in range(n):
        execution: tuple[str, str | None] = ("", None)

        def run() -> None:
            nonlocal execution
            execution = _execute(path)

        try:
            fingerprint = replay_run(cassette, run)
            output, failure = execution
            outputs.add(output)
            if failure != cassette.metadata.get("script_error"):
                raise Divergence(
                    len(cassette.boundaries),
                    f"script exception differs from recording: {failure or 'no exception'}",
                )
            if output != cassette.final_output:
                raise Divergence(len(cassette.boundaries), "script stdout differs from recording")
            hashes.add(fingerprint)
        except (RuntimeError, Divergence) as exc:
            return VerifyResult(False, index + 1, len(outputs), len(hashes), str(exc))
    passed = hashes == {cassette.fingerprint} and outputs == {cassette.final_output}
    return VerifyResult(
        passed,
        n,
        len(outputs),
        len(hashes),
        "Captured boundaries, redacted stdout and script outcome match; source checked",
    )


def fork_script(
    parent: Cassette,
    path: Path,
    *,
    at: int,
    value: Any,
    mocks: dict[tuple[str, str], Any],
    policy: SideEffectPolicy | None = None,
) -> Cassette:
    """Replay a trusted recorded script with one intervention and JSON-value mocks."""
    from contextlib import nullcontext
    from functools import partial

    from .boundary import Session
    from .capture import _patched
    from .fork import fork_run
    from .replay import Run
    from .sources import deterministic_sources

    check_source(parent.metadata, path)
    if parent.metadata.get("concurrent"):
        raise ValueError("concurrent forks are not supported; serialize this scenario")

    failure = None

    def execute(session: Session, transport: Any) -> str:
        nonlocal failure
        with (
            _patched(session),
            deterministic_sources(session) if parent.metadata.get("sources") else nullcontext(),
        ):
            output, failure = _execute(path)
            return output

    run: Run = execute
    from .fork import recorded_tool_mocks

    resolved = recorded_tool_mocks(
        parent, at=at, exclude=policy.live_allowlist if policy else frozenset()
    )
    resolved.update(
        {key: partial(lambda result, request: result, result) for key, result in mocks.items()}
    )
    if policy is not None:
        from .policy import fork_with_policy

        child = fork_with_policy(parent, run, at=at, value=value, mocks=resolved, policy=policy)
    else:
        child = fork_run(parent, run, at=at, value=value, mocks=resolved)
    child.metadata.pop("script_error", None)
    if failure is not None:
        child.metadata["script_error"] = failure
    child.metadata["tool_mock_policy"] = (
        "recorded outcomes by occurrence; unknown tools fail closed"
    )
    return child
