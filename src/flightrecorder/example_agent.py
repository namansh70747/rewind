"""A small example agent used to demonstrate and test the walking skeleton.

Phase 0 records *this* bundled agent (the plan's "one real single-tool agent"). It touches
every boundary kind — three LLM calls plus a clock read, a UUID, and an RNG draw — so a
faithful replay must reproduce all of them. Capturing an arbitrary, unmodified user agent
(global httpx interception) is Phase 1.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import httpx

from .boundary import Session
from .interceptors import RecordingTransport
from .providers import OPENAI, Messages, Provider

#: A run is a callable that, given a Session and an inner transport (or None for replay),
#: drives the agent and returns its final output string.
Run = Callable[[Session, httpx.BaseTransport | None], str]


def _first_int(text: str, default: int) -> int:
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else default


def _llm(
    client: httpx.Client, provider: Provider, model: str, api_key: str, messages: Messages
) -> str:
    resp = client.post(
        provider.url, headers=provider.headers(api_key), json=provider.body(model, messages)
    )
    resp.raise_for_status()
    return provider.extract(resp.json())


def _run_agent(
    session: Session, client: httpx.Client, provider: Provider, model: str, api_key: str
) -> str:
    run_id = session.new_uuid()
    started = session.now()
    jitter = session.rand()

    answer1 = _llm(
        client,
        provider,
        model,
        api_key,
        [
            {"role": "user", "content": "Reply with a single integer between 1 and 9."},
        ],
    )
    number = _first_int(answer1, default=3)
    doubled = number * 2  # deterministic local tool — not a boundary

    answer2 = _llm(
        client,
        provider,
        model,
        api_key,
        [
            {
                "role": "user",
                "content": f"I doubled {number} to get {doubled}. Reply with just: OK",
            },
        ],
    )
    answer3 = _llm(
        client,
        provider,
        model,
        api_key,
        [
            {"role": "user", "content": f"One short sentence confirming doubled={doubled}."},
        ],
    )

    return (
        f"run={run_id} t0={started:.0f} jitter={jitter:.4f} "
        f"n={number} doubled={doubled} ack={answer2.strip()!r} summary={answer3.strip()!r}"
    )


def make_example_run(
    provider: Provider = OPENAI, model: str | None = None, api_key: str = ""
) -> Run:
    """Bind the example agent to a provider/model; the returned callable is recorded/replayed."""
    resolved = model or provider.default_model

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        with httpx.Client(
            transport=RecordingTransport(session, inner), timeout=httpx.Timeout(30.0)
        ) as client:
            return _run_agent(session, client, provider, resolved, api_key)

    return run
