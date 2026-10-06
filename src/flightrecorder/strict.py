"""Strict replay: fail when agent code reads entropy the recorder did not capture.

A discarded ``time.time()``, ``random.random()``, ``uuid.uuid4()``, or ``os.urandom()``
does not change the boundary stream, so a non-strict replay can still match the
hash-chain and hide the leak. Strict mode raises :class:`Divergence` at that read and
names the source plus the boundary index.

Reads that go through :class:`~flightrecorder.boundary.Session` shims are allowed: the
immediate caller is this package. Reads whose immediate caller is the stdlib or an
installed library (httpx, ssl) are allowed too, so transport internals do not
false-positive. The agent's own frame is what fails.
"""

from __future__ import annotations

import inspect
import os
import random
import sysconfig
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from .boundary import Divergence, Session

if TYPE_CHECKING:
    from collections.abc import Iterator

_STDLIB = Path(sysconfig.get_path("stdlib")).resolve()
_PACKAGE = Path(__file__).resolve().parent


def _classify(filename: str) -> str:
    """Return ``recorder``, ``library``, or ``user`` for a stack filename."""
    if filename.startswith("<frozen"):
        return "library"
    if filename.startswith("<"):
        return "user"
    path = Path(filename).resolve()
    if path == _PACKAGE or _PACKAGE in path.parents:
        return "recorder"
    if "site-packages" in path.parts or "dist-packages" in path.parts:
        return "library"
    try:
        path.relative_to(_STDLIB)
    except ValueError:
        return "user"
    else:
        return "library"


def _refuse_if_uncaptured(session: Session, source: str) -> None:
    """Raise if the immediate caller outside this module is agent code."""
    for frame in inspect.stack()[1:]:
        if _classify(frame.filename) == "recorder" and Path(frame.filename).name == "strict.py":
            continue
        kind = _classify(frame.filename)
        if kind == "user":
            where = f"{Path(frame.filename).name}:{frame.lineno}"
            raise Divergence(
                session.boundary_index,
                f"uncaptured {source} at {where} — strict mode refuses a silent entropy read",
            )
        return


@contextmanager
def strict_guard(session: Session) -> Iterator[None]:
    """Patch the four uncaptured entropy sources for the duration of one replay."""
    original_time = time.time
    original_random = random.random
    original_uuid4 = uuid.uuid4
    original_urandom = os.urandom

    def guarded_time() -> float:
        _refuse_if_uncaptured(session, "time.time")
        return original_time()

    def guarded_random() -> float:
        _refuse_if_uncaptured(session, "random.random")
        return float(original_random())

    def guarded_uuid4() -> uuid.UUID:
        _refuse_if_uncaptured(session, "uuid.uuid4")
        return original_uuid4()

    def guarded_urandom(size: int) -> bytes:
        _refuse_if_uncaptured(session, "os.urandom")
        return original_urandom(size)

    time.time = guarded_time
    random.random = guarded_random
    uuid.uuid4 = guarded_uuid4
    os.urandom = guarded_urandom
    try:
        yield
    finally:
        time.time = original_time
        random.random = original_random
        uuid.uuid4 = original_uuid4
        os.urandom = original_urandom
