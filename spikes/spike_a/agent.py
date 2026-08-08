"""A tiny fixture agent plus the record / replay / verify orchestration.

The agent is intentionally small but touches every boundary kind we care about in
Week 1: three LLM HTTP calls (nondeterministic, temperature 0.7) plus a clock read, a
UUID, and an RNG draw. A deterministic local "tool" (doubling a number) is *not* a
boundary — re-executing it for free on replay is exactly the point.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .engine import Cassette, Divergence, RecordingTransport, Session

MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com"

Run = Callable[[Session, httpx.BaseTransport | None], str]


def _first_int(text: str, default: int) -> int:
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else default


def _llm(client: httpx.Client, base_url: str, api_key: str, messages: list[dict[str, str]]) -> str:
    resp = client.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": 0.7},
    )
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"])


def run_agent(session: Session, client: httpx.Client, base_url: str, api_key: str) -> str:
    """A 3-step agent whose output folds in clock/uuid/rng so replay must reproduce them."""
    run_id = session.new_uuid()
    started = session.now()
    jitter = session.rand()

    answer1 = _llm(
        client,
        base_url,
        api_key,
        [
            {"role": "user", "content": "Reply with a single integer between 1 and 9."},
        ],
    )
    number = _first_int(answer1, default=3)
    doubled = number * 2  # deterministic local tool — not a boundary

    answer2 = _llm(
        client,
        base_url,
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
        base_url,
        api_key,
        [
            {"role": "user", "content": f"One short sentence confirming doubled={doubled}."},
        ],
    )

    return (
        f"run={run_id} t0={started:.0f} jitter={jitter:.4f} "
        f"n={number} doubled={doubled} ack={answer2.strip()!r} summary={answer3.strip()!r}"
    )


def make_run(base_url: str = DEFAULT_BASE_URL, api_key: str = "") -> Run:
    """Bind an agent runner to an endpoint; the returned callable is what we record/replay."""

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        with httpx.Client(transport=RecordingTransport(session, inner)) as client:
            return run_agent(session, client, base_url, api_key)

    return run


def record(run: Run, inner: httpx.BaseTransport) -> Cassette:
    """Run once against the real (or mock) world, capturing every boundary."""
    session = Session("record")
    output = run(session, inner)
    return Cassette(boundaries=session.boundaries, fingerprint=session.chain, final_output=output)


def replay_once(cassette: Cassette, run: Run) -> tuple[str, str]:
    """Re-run the agent serving recorded values; returns (output, fingerprint)."""
    session = Session("replay", cassette)
    output = run(session, None)  # inner=None → network kill-switch
    session.assert_fully_consumed()
    return output, session.chain


@dataclass
class VerifyResult:
    passed: bool
    runs: int
    unique_outputs: int
    unique_fingerprints: int
    detail: str

    def __str__(self) -> str:
        verdict = "PASS ✅" if self.passed else "FAIL ❌"
        return (
            f"{verdict}  replays={self.runs}  distinct_outputs={self.unique_outputs}  "
            f"distinct_fingerprints={self.unique_fingerprints}\n  {self.detail}"
        )


def verify(cassette: Cassette, run: Run, n: int = 50) -> VerifyResult:
    """Replay ``n`` times; PASS iff every replay is byte-identical to the recording."""
    outputs: set[str] = set()
    fingerprints: set[str] = set()
    for i in range(n):
        try:
            output, fingerprint = replay_once(cassette, run)
        except Divergence as exc:
            return VerifyResult(False, n, len(outputs), len(fingerprints), f"replay {i}: {exc}")
        outputs.add(output)
        fingerprints.add(fingerprint)

    passed = outputs == {cassette.final_output} and fingerprints == {cassette.fingerprint}
    detail = (
        "all replays byte-identical to the recording; hash-chain matches"
        if passed
        else (
            f"MISMATCH — expected 1 output/fingerprint matching the recording, got "
            f"{len(outputs)} outputs / {len(fingerprints)} fingerprints"
        )
    )
    return VerifyResult(passed, n, len(outputs), len(fingerprints), detail)
