"""Record an UNMODIFIED agent script (`fr record -- python agent.py`) and replay it bit-exact.

The agent is a real standalone `.py` file written to a temp dir. It uses only `httpx` and a
multi-step tool flow (geocode → forecast → LLM) and knows nothing about flightrecorder. We
stub the HTTP transport so no network is needed, record the agent in-process, and prove it
replays bit-exact offline — the stub is never touched again on replay (kill-switch on).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest

from flightrecorder import RunStore, capture, verify_run
from flightrecorder.runner import (
    canonicalize_command,
    decode_command,
    encode_command,
    make_runner,
    parse_command,
)

_AGENT_SRC = """
import sys
import httpx

def main():
    city = sys.argv[1] if len(sys.argv) > 1 else "Delhi"
    with httpx.Client() as http:
        geo = http.get("https://geo.example/search", params={"name": city}).json()
        lat = geo["results"][0]["latitude"]
        wx = http.get("https://wx.example/forecast", params={"lat": lat}).json()
        temp = wx["current"]["temperature_2m"]
        ans = http.post(
            "https://llm.example/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": f"{city} {temp}"}]},
        ).json()
        print(ans["choices"][0]["message"]["content"])

if __name__ == "__main__":
    main()
"""


def _write_agent(tmp_path: Path) -> str:
    script = tmp_path / "agent.py"
    script.write_text(textwrap.dedent(_AGENT_SRC))
    return str(script)


def _stub_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "geo" in url:
            body: dict[str, Any] = {
                "results": [{"latitude": 28.6, "longitude": 77.2, "name": "Delhi"}]
            }
        elif "wx" in url:
            body = {"current": {"temperature_2m": 31.4, "precipitation": 0.0}}
        else:
            body = {"choices": [{"message": {"content": "Yes, take an umbrella."}}]}
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)


def test_record_and_replay_unmodified_agent_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_network(monkeypatch)
    argv = ["python", _write_agent(tmp_path), "Delhi"]

    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="nvidia", model="m", command=encode_command(argv)) as cap:
        make_runner(argv)()
    assert cap.cassette is not None
    assert cap.run_id is not None
    # geocode + forecast + llm = three captured HTTP boundaries.
    assert [b.kind for b in cap.cassette.boundaries] == ["http", "http", "http"]

    # The command round-trips through the store so `verify` can re-run the agent.
    loaded = store.load(cap.run_id)
    assert decode_command(loaded.command) == canonicalize_command(argv)

    # Replay 20x bit-exact, offline — the stub is never called again (kill-switch on).
    result = verify_run(loaded, make_runner(decode_command(loaded.command)), n=20)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1
    store.close()


def test_parse_command_forms(tmp_path: Path) -> None:
    script = _write_agent(tmp_path)
    abs_script = str(Path(script).resolve())
    assert parse_command(["python", script, "Delhi"]) == (abs_script, [abs_script, "Delhi"])
    assert parse_command(["python3", script]) == (abs_script, [abs_script])
    assert parse_command([script]) == (abs_script, [abs_script])
    with pytest.raises(ValueError, match="Python script"):
        parse_command(["ls", "-la"])
    with pytest.raises(ValueError, match="not found"):
        parse_command(["python", str(tmp_path / "nope.py")])


def test_command_survives_chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative argv at record time must still verify after the shell cwd changes."""
    _stub_network(monkeypatch)
    script = _write_agent(tmp_path)
    argv = ["python", script, "Delhi"]
    stored = canonicalize_command(argv)
    assert Path(stored[1]).is_absolute()

    store = RunStore(tmp_path / "runs.db")
    with capture(store, provider="nvidia", model="m", command=encode_command(argv)) as cap:
        make_runner(argv)()
    assert cap.run_id is not None
    loaded = store.load(cap.run_id)
    assert Path(decode_command(loaded.command)[1]).is_absolute()

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = verify_run(loaded, make_runner(decode_command(loaded.command)), n=5)
    assert result.passed, result.detail
    store.close()
