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
from .redaction import redact_text
from .replay import VerifyResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .boundary import Boundary
    from .policy import SideEffectPolicy
    from .store import RunStore


class CapturePersistenceError(RuntimeError):
    """A durable capture could not checkpoint or finalize."""


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute(path: Path) -> tuple[str, dict[str, Any]]:
    output = io.StringIO()
    original_argv, original_path = sys.argv[:], sys.path[:]
    try:
        sys.argv = [str(path)]
        sys.path.insert(0, str(path.resolve().parent))
        outcome: dict[str, Any] = {"version": 1, "kind": "exit", "code": 0}
        with redirect_stdout(output):
            try:
                runpy.run_path(str(path), run_name="__main__")
            except (Divergence, NetworkBlocked, CapturePersistenceError):
                raise
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    outcome["code"] = int(exc.code)
                elif exc.code is not None:
                    outcome.update(code=1, detail=redact_text(str(exc.code)))
            except Exception as exc:
                outcome.update(
                    kind="exception",
                    code=1,
                    exception_type=redact_text(f"{type(exc).__module__}.{type(exc).__qualname__}"),
                    detail=redact_text(str(exc)),
                )
        return redact_text(output.getvalue()), outcome
    finally:
        sys.argv = original_argv
        sys.path = original_path


def record_script(
    path: Path,
    *,
    concurrent: bool = False,
    sources: bool = False,
    on_boundary: Callable[[Boundary], None] | None = None,
) -> Cassette:
    """Executes trusted code. Only httpx clients created inside capture are intercepted."""
    digest = source_hash(path)
    with capture(
        provider="script",
        model=path.name,
        concurrent=concurrent,
        sources=sources,
        on_boundary=on_boundary,
    ) as cap:
        output, outcome = _execute(path)
    assert cap.cassette is not None
    cap.cassette.final_output = output
    cap.cassette.metadata = {
        **cap.cassette.metadata,
        **provenance(path),
        "source_sha256": digest,
        "terminal_outcome": outcome,
        "source_name": path.name,
        "capture_scope": "httpx + decorated tools + optional sources + redacted stdout",
    }
    return cap.cassette


def record_script_to_store(
    store: RunStore,
    path: Path,
    *,
    concurrent: bool = False,
    sources: bool = False,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, Cassette]:
    """Persist each completed boundary before returning its response to the agent."""
    if not path.is_file():
        raise ValueError("script source is unavailable")
    details = metadata or {}
    try:
        run_id = store.begin_script_capture(path.name, sample=bool(details.get("simulated")))
    except Exception as exc:
        raise CapturePersistenceError("Could not start a durable script capture.") from exc
    failed: CapturePersistenceError | None = None

    def checkpoint(boundary: Boundary) -> None:
        nonlocal failed
        if failed is not None:
            raise failed
        try:
            store.checkpoint_boundary(run_id, boundary)
        except Exception as exc:
            failed = CapturePersistenceError(f"Could not checkpoint capture {run_id}.")
            raise failed from exc

    cassette = record_script(path, concurrent=concurrent, sources=sources, on_boundary=checkpoint)
    if failed is not None:
        raise failed
    cassette.metadata.update(details)
    try:
        store.complete_script_capture(run_id, cassette)
    except Exception as exc:
        raise CapturePersistenceError(f"Could not finalize capture {run_id}.") from exc
    return run_id, cassette


def verify_script(cassette: Cassette, path: Path, n: int = 10) -> VerifyResult:
    if n < 1:
        raise ValueError("number of replays must be at least 1")
    if cassette.provider != "script":
        raise ValueError("recording is not a script")
    if cassette.metadata.get("capture_status") == "incomplete":
        raise ValueError("incomplete captures can be inspected but cannot be verified")
    check_source(cassette.metadata, path)
    outputs: set[str] = set()
    hashes: set[str] = set()
    expected_outcome = cassette.metadata.get("terminal_outcome")
    for index in range(n):
        observed: tuple[str, dict[str, Any]] | None = None

        def run() -> None:
            nonlocal observed
            observed = _execute(path)

        try:
            hashes.add(replay_run(cassette, run))
            assert observed is not None
            output, outcome = observed
            outputs.add(output)
            if expected_outcome is None and outcome["code"]:
                reason = "legacy recording cannot verify an unsuccessful outcome"
            elif expected_outcome is not None and outcome != expected_outcome:
                reason = "script terminal outcome differs from recording"
            else:
                reason = ""
            if reason:
                if outcome.get("detail"):
                    reason += f": {outcome['detail']}"
                raise Divergence(len(cassette.boundaries), reason)
            if output != cassette.final_output:
                raise Divergence(len(cassette.boundaries), "script stdout differs from recording")
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
        (
            "Boundaries, redacted stdout and terminal outcome match; source hash checked"
            if expected_outcome is not None
            else "Boundaries and redacted stdout match; legacy terminal outcome unavailable"
        ),
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

    terminal_outcome: dict[str, Any] = {}

    def execute(session: Session, transport: Any) -> str:
        with (
            _patched(session),
            deterministic_sources(session) if parent.metadata.get("sources") else nullcontext(),
        ):
            output, outcome = _execute(path)
            terminal_outcome.update(outcome)
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
    child.metadata["terminal_outcome"] = terminal_outcome
    child.metadata["tool_mock_policy"] = (
        "recorded outcomes by occurrence; unknown tools fail closed"
    )
    return child
