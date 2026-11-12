"""Explicit synthetic edit locations and weak labels for the Month 4 oracle."""

from __future__ import annotations

import copy
from functools import partial
from typing import Any

from flightrecorder.boundary import Cassette, Session

Event = tuple[str, str, Any, Any]


def recording(events: list[Event], output: str) -> Cassette:
    session = Session("record")
    for kind, key, request, response in events:
        session.mediate(kind, key, request, partial(lambda value: value, response))
    return Cassette(
        session.boundaries, session.chain, output, provider="synthetic", model="controlled-edit"
    )


def pairs() -> list[tuple[str, Cassette, Cassette, dict[str, Any]]]:
    rows = []

    def add(
        name: str,
        left: list[Event],
        right: list[Event],
        category: str | None,
        a: int | None,
        b: int | None,
        final_only: bool = False,
    ) -> None:
        rows.append(
            (
                name,
                recording(left, "PASS"),
                recording(right, "FAIL" if category else "PASS"),
                {"category": category, "a": a, "b": b, "final_only": final_only},
            )
        )

    prefix: list[Event] = [("tool", "prepare", {}, "ready")]
    quote: Event = ("tool", "quote", {"item": "GPU"}, 420)
    finish: Event = ("tool", "finish", {}, "done")
    add("identical", [quote], [quote], None, None, None)
    add(
        "tool-result",
        [*prefix, quote],
        [*prefix, ("tool", "quote", quote[2], 720)],
        "tool-result-drift",
        1,
        1,
    )
    add(
        "tool-argument",
        [*prefix, quote],
        [*prefix, ("tool", "quote", {"item": "CPU"}, 420)],
        "arg-hallucination",
        1,
        1,
    )
    add(
        "insert",
        [*prefix, quote],
        [*prefix, ("tool", "probe", {}, True), quote],
        "step-inserted",
        None,
        1,
    )
    add("delete", [*prefix, quote, finish], [*prefix, finish], "step-removed", 1, None)
    add("tool-choice", [quote], [("tool", "reserve", quote[2], 420)], "tool-choice", 0, 0)
    add(
        "retrieval",
        [("tool", "search", {"q": "GPU"}, ["a"])],
        [("tool", "search", {"q": "GPU"}, ["b"])],
        "retrieval-drift",
        0,
        0,
    )
    add("repeat", [quote, finish], [quote, quote, finish], "loop", None, 1)
    add(
        "sampling",
        [("llm", "decision", {"prompt": "choose"}, "a")],
        [("llm", "decision", {"prompt": "choose"}, "b")],
        "sampling-flake",
        0,
        0,
    )
    add(
        "truncation",
        [("llm", "decision", {}, {"finish_reason": "stop"})],
        [("llm", "decision", {}, {"finish_reason": "length"})],
        "truncation",
        0,
        0,
    )
    add(
        "cost",
        [("llm", "decision", {}, {"cost": 1})],
        [("llm", "decision", {}, {"cost": 4})],
        "cost-blowup",
        0,
        0,
    )
    add(
        "uuid-before-decision",
        [("uuid", "uuid4", None, "one"), quote],
        [("uuid", "uuid4", None, "two"), ("tool", "quote", quote[2], 720)],
        "tool-result-drift",
        1,
        1,
    )
    add("output-only", [quote], [quote], "agent-logic-drift", None, None, True)
    # A declared edit index independent of the diagnosis, across a longer run.
    events: list[Event] = [("tool", f"step-{i}", {"index": i}, i) for i in range(64)]
    for at in range(64):
        altered = copy.deepcopy(events)
        altered[at] = ("tool", f"step-{at}", {"index": at}, -1)
        add(f"hash-{at}", events, altered, "tool-result-drift", at, at)
    return rows
