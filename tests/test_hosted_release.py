"""Hosted request tests. A disposable PostgreSQL database enables the end-to-end cases."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from google.oauth2 import id_token

from flightrecorder.boundary import Cassette, Session
from flightrecorder.portable import envelope
from flightrecorder.product import hosted

if TYPE_CHECKING:
    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

ORIGIN = "https://rewind.example.test"
HEADERS = {"Origin": ORIGIN}


def test_hosted_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REWIND_PUBLIC_ORIGIN", raising=False)
    client = hosted.app.test_client()
    assert client.get("/health").status_code == 503
    assert client.get("/").status_code == 503
    assert client.get("/api/v1/runs").status_code == 503


@pytest.mark.parametrize("open_signup", [False, True])
def test_hosted_workspace(monkeypatch: pytest.MonkeyPatch, open_signup: bool) -> None:
    database = os.getenv("REWIND_TEST_DATABASE")
    if not database:
        pytest.skip("Set REWIND_TEST_DATABASE to an empty disposable PostgreSQL database")
    for key, value in {
        "DATABASE_URL": database,
        "REWIND_PUBLIC_ORIGIN": ORIGIN,
        "REWIND_ALLOWED_EMAILS": "" if open_signup else "one@example.test,two@example.test",
        "REWIND_OPEN_SIGNUP": "1" if open_signup else "0",
        "GOOGLE_CLIENT_ID": "test.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test",
        "REWIND_BUILD_ID": "test-candidate",
    }.items():
        monkeypatch.setenv(key, value)
    recording = Session("record")
    recording.mediate("tool", "release_check", {}, lambda: {"rollback_plan": False})
    bundle = envelope(
        Cassette(
            boundaries=recording.boundaries,
            fingerprint=recording.chain,
            final_output="blocked",
            metadata={"script_error": "missing rollback plan", "product_source": "private.py"},
        )
    )
    with hosted.connection(hosted.configuration()) as db:
        db.execute(hosted.RESOURCE.joinpath("hosted.sql").read_text(encoding="utf-8"))
        demo = hosted.save_recording(db, bundle, None)

    left = hosted.app.test_client()
    right = hosted.app.test_client()
    visitor = hosted.app.test_client()
    account_namespace = uuid4().hex

    def start(browser: FlaskClient, mode: str) -> dict[str, list[str]]:
        response = browser.get("/auth/google?mode=" + mode, base_url=ORIGIN)
        assert response.status_code == 302
        assert "Secure" in response.headers["Set-Cookie"]
        return parse_qs(urlsplit(response.location or "").query)

    def finish(browser: FlaskClient, params: dict[str, list[str]], user: str) -> str:
        def exchange(*args: object, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200, json={"id_token": "fixture"}, request=httpx.Request("POST", ORIGIN)
            )

        monkeypatch.setattr(httpx, "post", exchange)
        monkeypatch.setattr(
            id_token,
            "verify_oauth2_token",
            lambda *_: {
                "nonce": params["nonce"][0],
                "sub": account_namespace + user,
                "email": user + "@example.test",
                "email_verified": True,
            },
        )
        response = browser.get(
            hosted.CALLBACK,
            query_string={"state": params["state"][0], "code": "fixture"},
            base_url=ORIGIN,
        )
        return response.location or ""

    assert visitor.get("/health", base_url=ORIGIN).json == {
        "build": "test-candidate",
        "ready": True,
    }
    assert visitor.get("/api/v1/runs", base_url=ORIGIN).status_code == 401
    cancelled = start(visitor, "signup")
    response = visitor.get(
        hosted.CALLBACK,
        base_url=ORIGIN,
        query_string={"state": cancelled["state"][0], "error": "access_denied"},
    )
    assert response.location == "/?problem=cancelled"
    assert finish(visitor, start(visitor, "signup"), "outsider") == (
        "/" if open_signup else "/?problem=invite"
    )
    assert finish(left, start(left, "signin"), "one") == "/?problem=signup"
    params = start(left, "signup")
    assert finish(right, params, "one") == "/?problem=expired"
    assert finish(left, params, "one") == "/"
    assert finish(left, params, "one") == "/?problem=expired"
    assert finish(right, start(right, "signup"), "two") == "/"
    assert left.get("/", base_url=ORIGIN).status_code == 200

    def api(browser: FlaskClient, operation: str, data: object = None) -> TestResponse:
        path = "/api/v1/" + operation
        if data is None:
            return browser.get(path, base_url=ORIGIN)
        session = browser.get("/api/v1/session", base_url=ORIGIN).get_json()
        return browser.post(
            path,
            base_url=ORIGIN,
            json=data,
            headers={**HEADERS, "X-Rewind-Token": session["token"]},
        )

    assert api(left, "runs/" + demo).status_code == 200
    assert api(right, "runs/" + demo).status_code == 200
    imported = api(left, "import", {"recording": bundle})
    assert imported.status_code == 201
    private = imported.get_json()["run_id"]
    assert api(left, "compare", {"left": private, "right": demo}).status_code == 200
    assert api(left, "export", {"run_id": private}).status_code == 200
    assert api(right, "runs/" + private).status_code == 404
    assert api(right, "compare", {"left": demo, "right": private}).status_code == 404
    assert api(right, "export", {"run_id": private}).status_code == 404
    assert api(left, "import", {"recording": {**bundle, "checksum": "invalid"}}).status_code == 400
    assert api(left, "import", {"recording": {**bundle, "format": "unknown"}}).status_code == 400
    assert (
        api(left, "import", {"recording": {"too_large": "x" * (hosted.LIMIT + 100)}}).status_code
        == 413
    )
    assert left.post("/api/v1/import", base_url=ORIGIN, json={}).status_code == 403
    assert api(left, "capture", {}).status_code == 404

    token = left.get_cookie(hosted.SESSION, domain="rewind.example.test")
    assert token is not None
    another_instance = hosted.app.test_client()
    another_instance.set_cookie(hosted.SESSION, token.value, domain="rewind.example.test")
    assert api(another_instance, "runs/" + private).status_code == 200
    csrf = api(left, "session").get_json()["token"]
    assert (
        left.post(
            "/auth/sign-out", base_url=ORIGIN, headers=HEADERS, data={"csrf": csrf}
        ).status_code
        == 302
    )
    assert api(another_instance, "runs").status_code == 401
    assert finish(left, start(left, "signin"), "one") == "/"
    token = left.get_cookie(hosted.SESSION, domain="rewind.example.test")
    assert token is not None
    with hosted.connection(hosted.configuration()) as db:
        db.execute(
            "UPDATE rewind_session SET expires = now() WHERE token_hash = %s",
            (hosted.digest(token.value),),
        )
    assert api(left, "runs").status_code == 401
