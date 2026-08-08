"""A tiny fixture agent plus the record / replay / verify orchestration.

Provider-agnostic by design: capture happens at the httpx transport layer
(ADR-0007), so the *only* thing that differs between OpenAI and Anthropic is how the
LLM HTTP call is shaped and parsed. The agent touches every Week-1 boundary kind:
three LLM calls (temperature 0.7) plus a clock read, a UUID, and an RNG draw. A
deterministic local "tool" (doubling a number) is *not* a boundary.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from .engine import Cassette, Divergence, RecordingTransport, Session

Run = Callable[[Session, httpx.BaseTransport | None], str]
Messages = list[dict[str, str]]


@dataclass(frozen=True)
class Provider:
    """Everything that differs between LLM vendors — the rest of the code is shared."""

    name: str
    url: str
    default_model: str
    key_env: str


OPENAI = Provider(
    name="openai",
    url="https://api.openai.com/v1/chat/completions",
    default_model="gpt-4o-mini",
    key_env="OPENAI_API_KEY",
)
ANTHROPIC = Provider(
    name="anthropic",
    url="https://api.anthropic.com/v1/messages",
    default_model="claude-haiku-4-5-20251001",
    key_env="ANTHROPIC_API_KEY",
)
# NVIDIA's API catalog is OpenAI-compatible (same chat/completions shape + Bearer auth),
# so it reuses the OpenAI request/response path below.
NVIDIA = Provider(
    name="nvidia",
    url="https://integrate.api.nvidia.com/v1/chat/completions",
    default_model="meta/llama-3.1-8b-instruct",
    key_env="NVIDIA_API_KEY",
)
PROVIDERS = {p.name: p for p in (OPENAI, ANTHROPIC, NVIDIA)}


def _headers(provider: Provider, api_key: str) -> dict[str, str]:
    if provider.name == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    return {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}


def _body(provider: Provider, model: str, messages: Messages) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "temperature": 0.7, "messages": messages}
    if provider.name == "anthropic":
        body["max_tokens"] = 64  # required by the Anthropic Messages API
    return body


def _extract(provider: Provider, data: Any) -> str:
    if provider.name == "anthropic":
        return str(data["content"][0]["text"])
    return str(data["choices"][0]["message"]["content"])


def _first_int(text: str, default: int) -> int:
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else default


def _llm(
    client: httpx.Client, provider: Provider, model: str, api_key: str, messages: Messages
) -> str:
    resp = client.post(
        provider.url, headers=_headers(provider, api_key), json=_body(provider, model, messages)
    )
    resp.raise_for_status()
    return _extract(provider, resp.json())


def run_agent(
    session: Session, client: httpx.Client, provider: Provider, model: str, api_key: str
) -> str:
    """A 3-step agent whose output folds in clock/uuid/rng so replay must reproduce them."""
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


def make_run(provider: Provider = OPENAI, model: str | None = None, api_key: str = "") -> Run:
    """Bind an agent runner to a provider/model; the returned callable is recorded/replayed."""
    resolved = model or provider.default_model

    def run(session: Session, inner: httpx.BaseTransport | None) -> str:
        with httpx.Client(
            transport=RecordingTransport(session, inner), timeout=httpx.Timeout(30.0)
        ) as client:
            return run_agent(session, client, provider, resolved, api_key)

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
