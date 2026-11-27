"""Exercise the network demo's private worker using an isolated PostgreSQL database."""

from __future__ import annotations

import os
from time import monotonic, sleep
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from flightrecorder.product import hosted
from flightrecorder.product.demo import Demo

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

ORIGIN = "https://demo.example.test"


def test_remote_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    database = os.getenv("REWIND_TEST_DATABASE")
    if not database:
        pytest.skip("Set REWIND_TEST_DATABASE to a disposable PostgreSQL database")
    config = hosted.Config(
        ORIGIN,
        "demo.apps.googleusercontent.com",
        "test",
        database,
        frozenset({"first@example.test", "second@example.test"}),
        False,
    )
    monkeypatch.setattr(hosted, "configuration", lambda: config)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("REWIND_DEMO_PROVIDER", "groq")
    demo = Demo(config)
    demo.migrate()
    monkeypatch.setitem(hosted.app.config, "REWIND_DEMO", demo)

    def browser(email: str) -> FlaskClient:
        token = uuid4().hex
        with hosted.connection(config) as db:
            db.execute("INSERT INTO rewind_account VALUES (%s, %s)", (token, email))
            db.execute(
                "INSERT INTO rewind_session VALUES (%s, %s, %s, now() + interval '1 hour')",
                (hosted.digest(token), token, "csrf-" + token),
            )
        client = hosted.app.test_client()
        client.set_cookie(hosted.SESSION, token, domain="demo.example.test")
        return client

    first = browser("first@example.test")
    second = browser("second@example.test")

    def get(client: FlaskClient, operation: str) -> TestResponse:
        return client.get("/api/v1/" + operation, base_url=ORIGIN)

    def post(client: FlaskClient, operation: str, body: dict[str, object]) -> TestResponse:
        csrf = get(client, "session").get_json()["token"]
        return client.post(
            "/api/v1/" + operation,
            json=body,
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "X-Rewind-Token": csrf},
        )

    def wait_for_done(identifier: str) -> dict[str, object]:
        deadline = monotonic() + 15
        while monotonic() < deadline:
            for row in get(first, "jobs").get_json()["jobs"]:
                if row["id"] == identifier and row["status"] not in {"queued", "running"}:
                    assert isinstance(row, dict)
                    return row
            sleep(0.15)
        pytest.fail("Demo worker did not finish in 15 seconds.")

    def capture(source: str) -> str:
        response = post(first, "capture", {"source": source, "trusted": True})
        assert response.status_code == 202, response.get_json()
        identifier = response.get_json()["job_id"]
        job = wait_for_done(identifier)
        assert job["status"] == "completed", job
        result = job["result"]
        assert isinstance(result, dict)
        return str(result["run_id"])

    pending = post(first, "capture", {"source": "release-ready", "trusted": True})
    assert pending.status_code == 202
    pending_id = pending.get_json()["job_id"]
    assert post(second, "capture", {"source": "release-ready", "trusted": True}).status_code == 409
    assert post(second, "cancel", {"job_id": pending_id}).status_code == 404
    assert post(first, "cancel", {"job_id": pending_id}).get_json()["status"] == "cancelled"

    demo.start()
    try:
        assert first.get("/health", base_url=ORIGIN).get_json()["ready"]
        assert b'data-demo="true"' in first.get("/", base_url=ORIGIN).data
        assert [script["value"] for script in get(first, "scripts").get_json()["scripts"]] == [
            "release-ready",
            "release-blocked",
        ]
        assert post(first, "capture", {"source": "../test.py", "trusted": True}).status_code == 400
        assert (
            post(
                first, "capture", {"source": "release-ready", "trusted": True, "args": []}
            ).status_code
            == 400
        )
        assert post(first, "provider-check", {"provider": "groq"}).status_code == 400
        healthy = capture("release-ready")
        failed = capture("release-blocked")
        run = get(first, "runs/" + failed).get_json()["run"]
        assert "rollback_plan" in run["metadata"]["script_error"]
        assert "product_source" not in run["metadata"]
        assert get(second, "runs/" + failed).status_code == 404
        assert post(second, "export", {"run_id": failed}).status_code == 404
        assert not get(second, "jobs").get_json()["jobs"]
        assert post(second, "compare", {"left": healthy, "right": failed}).status_code == 404
        assert post(second, "verify", {"run_id": failed, "replays": 1}).status_code == 404

        comparison = post(first, "compare", {"left": healthy, "right": failed})
        assert comparison.status_code == 200
        assert comparison.get_json()["comparison"]["alignment"]
        replay = post(first, "verify", {"run_id": failed, "replays": 3})
        assert replay.status_code == 202, replay.get_json()
        job = wait_for_done(replay.get_json()["job_id"])
        result = job["result"]
        assert job["status"] == "completed" and isinstance(result, dict) and result["passed"], job
        runs = get(first, "runs").get_json()["runs"]
        assert any(row["id"] == failed and row["verification"]["passed"] for row in runs)

        exported = post(first, "export", {"run_id": failed}).get_json()
        imported = post(first, "import", {"recording": exported}).get_json()["run_id"]
        assert post(first, "verify", {"run_id": imported, "replays": 1}).status_code == 404
        assert post(first, "corpus-audit", {}).get_json()["passed"]

        demo.closed.set()
        demo.thread.join(timeout=10)
        interrupted = post(first, "capture", {"source": "release-ready", "trusted": True})
        assert interrupted.status_code == 202
        demo = Demo(config)
        monkeypatch.setitem(hosted.app.config, "REWIND_DEMO", demo)
        demo.start()
        restarted = wait_for_done(interrupted.get_json()["job_id"])
        assert restarted["status"] == "failed"
        assert "restarted" in str(restarted["error"])
        assert get(first, "runs/" + failed).status_code == 200
    finally:
        demo.closed.set()
        demo.thread.join(timeout=10)
