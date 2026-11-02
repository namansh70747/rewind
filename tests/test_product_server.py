"""Local console API: trusted capture, replay, portability and request isolation."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

import httpx

from flightrecorder.product.server import ProductServer


def test_product_capture_verify_and_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "agent.py"
    monkeypatch.setenv("NVIDIA_API_KEY", "private-test-key-123")
    # No external network needed: this trusted script only uses a controlled local transport.
    source.write_text(
        "import httpx, os\n"
        "with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text='hello'))) as client:\n"
        "    print(client.get('https://example.test').text, os.environ['NVIDIA_API_KEY'])\n"
    )
    server = ProductServer(("127.0.0.1", 0), tmp_path, tmp_path / "runs.db")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    headers = {"X-Rewind-Token": server.token, "Origin": url}
    try:
        with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
            assert (
                client.post(
                    "/api/v1/capture", json={"source": "agent.py", "trusted": True}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/capture",
                    headers=headers,
                    json={"source": "../bad.py", "trusted": True},
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/v1/capture", headers=headers, json={"source": "agent.py"}
                ).status_code
                == 400
            )
            response = client.post(
                "/api/v1/capture", headers=headers, json={"source": "agent.py", "trusted": True}
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            for _ in range(100):
                jobs = client.get("/api/v1/jobs").json()["jobs"]
                job = next(item for item in jobs if item["id"] == job_id)
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.05)
            assert job["status"] == "completed", job
            run_id = job["result"]["run_id"]
            assert (
                client.get("/api/v1/runs/" + run_id).json()["run"]["final_output"]
                == "hello <redacted:custom>\n"
            )
            response = client.post(
                "/api/v1/verify", headers=headers, json={"run_id": run_id, "replays": 3}
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            for _ in range(100):
                jobs = client.get("/api/v1/jobs").json()["jobs"]
                job = next(item for item in jobs if item["id"] == job_id)
                if job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.05)
            assert job["status"] == "completed" and job["result"]["passed"], job
            exported = client.post(
                "/api/v1/export", headers=headers, json={"run_id": run_id}
            ).json()
            assert "private-test-key-123" not in str(exported)
            assert "product_source" not in exported["run"]["metadata"]
            imported = client.post(
                "/api/v1/import", headers=headers, json={"recording": exported}
            ).json()["run_id"]
            assert (
                client.post(
                    "/api/v1/verify", headers=headers, json={"run_id": imported}
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/v1/compare", headers=headers, json={"left": run_id, "right": imported}
                ).status_code
                == 200
            )
            assert (
                client.post(
                    "/api/v1/cancel",
                    headers={**headers, "Origin": "https://evil.example"},
                    json={"job_id": job_id},
                ).status_code
                == 403
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
