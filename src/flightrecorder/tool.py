"""``@fr.tool`` — mark a Python function as a recorded tool boundary (Week 3 plan).

When an active :class:`~flightrecorder.boundary.Session` is recording/replaying
(via the Session API or an active ``capture()`` that exposes the session), the
decorator mediates the call as ``kind=tool``. Outside a session it is a no-op wrap.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def tool(fn: Callable[P, R]) -> Callable[P, R]:
    """Decorator: record/replay this callable as a ``tool`` boundary when a session is active."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        from .capture import active_session

        session = active_session()
        if session is None:
            return fn(*args, **kwargs)
        request = {"args": list(args), "kwargs": dict(kwargs)}
        return session.mediate("tool", fn.__name__, request, lambda: fn(*args, **kwargs))

    wrapper.__fr_tool__ = True  # type: ignore[attr-defined]
    return wrapper
