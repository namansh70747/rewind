"""NVIDIA example records via the adapter and replays without a credential."""

import importlib.util
from pathlib import Path

import httpx

from flightrecorder.portable import export_run, import_run
from flightrecorder.replay import record, verify


def test_nvidia_capture_and_offline_replay(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "nvidia_agent.py"
    spec = importlib.util.spec_from_file_location("nvidia_agent", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "synthetic-test-credential"

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer " + secret
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "A recorded answer"}}]}
        )

    cassette = record(
        module.make_run(module.MODEL, secret),
        httpx.MockTransport(respond),
        provider="nvidia",
        model=module.MODEL,
    )
    path = tmp_path / "recording.json"
    export_run(cassette, path)
    assert secret not in path.read_text()
    assert verify(import_run(path), module.make_run(module.MODEL, ""), 50).passed
