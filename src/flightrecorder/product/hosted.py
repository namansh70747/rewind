"""Request-only hosted Rewind workspace."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import secrets
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from importlib.resources import files
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
import psycopg
from flask import Flask, Response, g, jsonify, request
from flask.json.provider import DefaultJSONProvider
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from psycopg.types.json import Jsonb
from werkzeug.exceptions import HTTPException

from flightrecorder.boundary import Divergence, canon
from flightrecorder.diagnosis import diagnose
from flightrecorder.portable import envelope, parse_envelope

if TYPE_CHECKING:
    from collections.abc import Iterator

    from werkzeug.wrappers import Response as BaseResponse

    from flightrecorder.product.demo import Demo

app = Flask(__name__, static_folder=None)
app.logger.setLevel(logging.INFO)
assert isinstance(app.json, DefaultJSONProvider)
app.json.ensure_ascii = False
LIMIT = 1_500_000
COMPARE_LIMIT = 200
app.config["MAX_CONTENT_LENGTH"] = LIMIT + 100
RESOURCE = files("flightrecorder.product")
SESSION = "__Host-rewind-session"
BROWSER = "__Host-rewind-oauth"
CALLBACK = "/auth/google/callback"
PROBLEMS = {
    "cancelled": "Google sign-in was cancelled. Try again when ready.",
    "expired": "This sign-in attempt expired. Start again from this page.",
    "invite": "Choose the Google account invited to this workspace.",
    "signup": "Create your workspace with Sign up with Google first.",
    "google": "Google sign-in is temporarily unavailable. Try again.",
}


@dataclass(frozen=True)
class Config:
    origin: str
    client: str
    secret: str
    database: str
    invites: frozenset[str]
    open_signup: bool

    def allows(self, email: str) -> bool:
        return self.open_signup or email.casefold() in self.invites


def configuration() -> Config:
    origin = os.getenv("REWIND_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    invites = frozenset(
        value.strip().casefold()
        for value in os.getenv("REWIND_ALLOWED_EMAILS", "").split(",")
        if value.strip()
    )
    open_signup = os.getenv("REWIND_OPEN_SIGNUP", "0")
    client = os.getenv("GOOGLE_CLIENT_ID", "")
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    database = os.getenv("DATABASE_URL", "")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not re.fullmatch(r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?", origin)
        or not client.endswith(".apps.googleusercontent.com")
        or not secret.strip()
        or not database.startswith(("postgresql://", "postgres://"))
        or open_signup not in {"0", "1"}
        or (open_signup == "0" and not invites)
        or not all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) for email in invites)
    ):
        raise ValueError("Hosted configuration is incomplete")
    return Config(origin, client, secret, database, invites, open_signup == "1")


@contextmanager
def connection(config: Config) -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    with psycopg.connect(config.database, connect_timeout=4, prepare_threshold=None) as db:
        db.execute("SET LOCAL statement_timeout = 5000")
        yield db


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cookie(response: BaseResponse, name: str, value: str, age: int) -> BaseResponse:
    response.set_cookie(
        name, value, max_age=age, secure=True, httponly=True, samesite="Lax", path="/"
    )
    return response


def unavailable() -> Response | tuple[Response, int]:
    if request.path == "/" or request.path.startswith("/auth/"):
        return Response(
            "<h1>Workspace temporarily unavailable</h1><p>Try again in a moment.</p>"
            '<a href="/">Retry</a>',
            status=503,
            mimetype="text/html",
        )
    return jsonify(error="Workspace temporarily unavailable. Try again."), 503


@app.before_request
def measure() -> None:
    g.rewind_started = time.monotonic()
    g.rewind_id = uuid4().hex


@app.after_request
def headers(response: Response) -> Response:
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Request-ID": g.rewind_id,
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'",
        }
    )
    app.logger.info(
        "request=%s route=%s status=%s duration_ms=%d",
        g.rewind_id,
        request.endpoint or "unknown",
        response.status_code,
        (time.monotonic() - g.rewind_started) * 1000,
    )
    return response


@app.errorhandler(Exception)
def recover(error: Exception) -> Response | tuple[Response, int]:
    if isinstance(error, HTTPException):
        message = {
            400: "Invalid request.",
            401: "Sign in to continue.",
            403: "Refresh the workspace and try again.",
            404: "Recording or route not found.",
            405: "Method not allowed.",
            413: "This bundle exceeds the hosted limit. Open it in local Rewind.",
        }.get(error.code or 500, "Workspace request failed.")
        return jsonify(error=message), error.code or 500
    app.logger.warning("request=%s error_type=%s", g.rewind_id, type(error).__name__)
    return unavailable()


def identity(
    db: psycopg.Connection[tuple[Any, ...]], config: Config
) -> tuple[str, str, str] | None:
    token = request.cookies.get(SESSION)
    if not token:
        return None
    row = db.execute(
        """SELECT a.subject, a.email, s.csrf FROM rewind_session s
           JOIN rewind_account a ON a.subject = s.subject
           WHERE s.token_hash = %s AND s.expires > now()""",
        (digest(token),),
    ).fetchone()
    return (row[0], row[1], row[2]) if row and config.allows(row[1]) else None


@app.get("/health")
def health() -> tuple[Response, int]:
    build = os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("REWIND_BUILD_ID") or "development"
    try:
        with connection(configuration()) as db:
            ready = (
                db.execute("SELECT 1 FROM rewind_schema WHERE version = 1").fetchone() is not None
            )
    except (ValueError, psycopg.Error):
        ready = False
    demo = cast("Demo | None", app.config.get("REWIND_DEMO"))
    ready = ready and (demo is None or demo.thread.is_alive())
    return jsonify(build=build, ready=ready), 200 if ready else 503


@app.get("/")
def home() -> Response:
    config = configuration()
    with connection(config) as db:
        account = identity(db, config)
        if not account:
            return Response(
                RESOURCE.joinpath("hosted-sign-in.html")
                .read_text(encoding="utf-8")
                .replace("__MESSAGE__", PROBLEMS.get(request.args.get("problem", ""), "")),
                mimetype="text/html",
            )
    html = RESOURCE.joinpath("index.html").read_text(encoding="utf-8")
    mode = ""
    if app.config.get("REWIND_DEMO"):
        mode = ' data-demo="true"'
        html = html.replace(
            "The selected script runs on this machine. It can access files, network services, "
            "and provider accounts with your permissions.",
            "The selected script runs on the demo host. Only approved scripts are available.",
        ).replace(
            "Manage appearance and review what Rewind stores locally.",
            "Manage appearance and review your demo workspace.",
        )
    return Response(
        html.replace("<body", '<body data-hosted="true"' + mode, 1)
        .replace("__REWIND_TOKEN__", account[2])
        .replace("__REWIND_SIGN_OUT__", "")
        .replace("Local workspace", "Hosted workspace")
        .replace("SQLite on this device", "Google sign-in required")
        .replace('method="post" ><button type="submit"', 'method="post"><button type="submit"')
        .replace(
            'action="/auth/sign-out" method="post">',
            'action="/auth/sign-out" method="post"><input type="hidden" name="csrf" value="'
            + account[2]
            + '">',
        ),
        mimetype="text/html",
    )


@app.get("/<asset>")
def asset_file(asset: str) -> Response | tuple[Response, int]:
    types = {
        "workspace.js": "text/javascript",
        "workspace.css": "text/css",
        "rewind-mark.png": "image/png",
        "rewind-mark.svg": "image/svg+xml",
    }
    if asset not in types:
        return jsonify(error="Not found."), 404
    return Response(RESOURCE.joinpath(asset).read_bytes(), mimetype=types[asset])


@app.get("/auth/google")
def oauth_start() -> BaseResponse:
    config = configuration()
    action = request.args.get("mode", "signin")
    if action not in {"signup", "signin"}:
        return app.redirect("/?problem=expired")
    browser, state, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(4))
    with connection(config) as db:
        db.execute("DELETE FROM rewind_oauth WHERE expires <= now()")
        db.execute(
            """INSERT INTO rewind_oauth VALUES
               (%s, %s, %s, %s, %s, now() + interval '10 minutes')""",
            (digest(state), digest(browser), verifier, nonce, action),
        )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    query = urlencode(
        {
            "client_id": config.client,
            "redirect_uri": config.origin + CALLBACK,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return cookie(
        app.redirect("https://accounts.google.com/o/oauth2/v2/auth?" + query), BROWSER, browser, 600
    )


class GoogleRequest(Request):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = 5
        return super().__call__(*args, **kwargs)  # type: ignore[no-untyped-call]


@app.get(CALLBACK)
def oauth_callback() -> BaseResponse:
    config = configuration()
    browser = request.cookies.get(BROWSER, "")
    state = request.args.get("state", "")
    with connection(config) as db:
        attempt = db.execute(
            """DELETE FROM rewind_oauth
               WHERE state = %s AND browser_hash = %s AND expires > now()
               RETURNING verifier, nonce, action""",
            (digest(state), digest(browser)),
        ).fetchone()
    if not attempt:
        return oauth_problem("expired")
    if request.args.get("error") == "access_denied":
        return oauth_problem("cancelled")
    code = request.args.get("code")
    if not code:
        return oauth_problem("google")
    try:
        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": config.client,
                "client_secret": config.secret,
                "redirect_uri": config.origin + CALLBACK,
                "grant_type": "authorization_code",
                "code_verifier": attempt[0],
            },
            timeout=5,
        )
        token_response.raise_for_status()
        claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            token_response.json()["id_token"],
            GoogleRequest(),
            config.client,
        )
        if claims.get("nonce") != attempt[1]:
            return oauth_problem("expired")
        email = claims["email"].casefold()
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject:
            return oauth_problem("google")
        if claims.get("email_verified") is not True or not config.allows(email):
            return oauth_problem("invite")
    except Exception:
        return oauth_problem("google")
    session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with connection(config) as db:
        if attempt[2] == "signup":
            db.execute(
                "INSERT INTO rewind_account VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (subject, email),
            )
        if not db.execute(
            "UPDATE rewind_account SET email = %s WHERE subject = %s RETURNING subject",
            (email, subject),
        ).fetchone():
            return oauth_problem("signup")
        db.execute(
            "DELETE FROM rewind_session WHERE expires <= now() OR token_hash = %s",
            (digest(request.cookies.get(SESSION, "")),),
        )
        db.execute(
            "INSERT INTO rewind_session VALUES (%s, %s, %s, now() + interval '12 hours')",
            (digest(session), subject, csrf),
        )
    return cookie(cookie(app.redirect("/"), BROWSER, "", 0), SESSION, session, 43200)


def oauth_problem(reason: str) -> BaseResponse:
    app.logger.info("request=%s oauth_callback=%s", g.rewind_id, reason)
    return cookie(app.redirect("/?problem=" + reason), BROWSER, "", 0)


@app.post("/auth/sign-out")
def sign_out() -> BaseResponse | tuple[Response, int]:
    config = configuration()
    with connection(config) as db:
        account = identity(db, config)
        if account and (
            request.headers.get("Origin") != config.origin or request.form.get("csrf") != account[2]
        ):
            return jsonify(error="Refresh the workspace and try again."), 403
        if account:
            db.execute(
                "DELETE FROM rewind_session WHERE token_hash = %s",
                (digest(request.cookies[SESSION]),),
            )
    return cookie(app.redirect("/"), SESSION, "", 0)


def prepare_bundle(obj: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(canon(obj)) > LIMIT:
        raise ValueError("This bundle exceeds the hosted limit. Open it in local Rewind.")
    cassette = parse_envelope(obj)
    if any(len(value) > 300 for value in (cassette.provider, cassette.model)):
        raise ValueError("Recording provider or model label is too long.")
    verification = cassette.metadata.get("verification")
    valid_verification = (
        isinstance(verification, dict)
        and type(verification.get("passed")) is bool
        and type(verification.get("replays")) is int
        and verification["replays"] > 0
        and isinstance(verification.get("checked_at"), str)
    )
    cassette.metadata = {
        key: value
        for key, value in cassette.metadata.items()
        if key
        in {
            "script_error",
            "product_provider",
            "product_model",
            "counterfactual",
            "parent_fingerprint",
            "fork_at",
            "continuation_policy",
            "simulated",
        }
    }
    if valid_verification and isinstance(verification, dict):
        cassette.metadata["verification"] = {
            key: verification[key] for key in ("passed", "replays", "checked_at")
        }
    metadata = cassette.metadata
    for key in ("product_provider", "product_model"):
        if key in metadata and (not isinstance(metadata[key], str) or len(metadata[key]) > 300):
            metadata.pop(key)
    if not metadata.get("counterfactual"):
        for key in ("parent_fingerprint", "fork_at", "continuation_policy"):
            metadata.pop(key, None)
    summary = {
        "provider": cassette.provider,
        "model": cassette.model,
        "display_provider": metadata.get("product_provider", cassette.provider),
        "display_model": metadata.get("product_model", cassette.model),
        "fingerprint": cassette.fingerprint,
        "n_boundaries": len(cassette.boundaries),
        "verification": metadata.get("verification"),
        "counterfactual": bool(metadata.get("counterfactual")),
        "script_failed": isinstance(metadata.get("script_error"), str),
        "sample": bool(metadata.get("simulated")) or cassette.provider == "demo",
        "has_source": False,
    }
    return envelope(cassette), summary


def save_recording(db: psycopg.Connection[tuple[Any, ...]], obj: Any, owner: str | None) -> str:
    bundle, summary = prepare_bundle(obj)
    identifier = uuid4()
    db.execute(
        "INSERT INTO rewind_recording (id, owner, demo, bundle, summary) VALUES (%s,%s,%s,%s,%s)",
        (identifier, owner, owner is None, Jsonb(bundle), Jsonb(summary)),
    )
    return identifier.hex


def recording(
    db: psycopg.Connection[tuple[Any, ...]], subject: str, value: Any
) -> tuple[Any, ...] | None:
    try:
        identifier = UUID(value)
    except (ValueError, TypeError, AttributeError):
        return None
    return db.execute(
        "SELECT bundle FROM rewind_recording WHERE id = %s AND (owner = %s OR demo)",
        (identifier, subject),
    ).fetchone()


@app.route("/api/v1/<path:operation>", methods=["GET", "POST"])
def evidence_api(operation: str) -> Response | tuple[Response, int]:
    config = configuration()
    with connection(config) as db:
        account = identity(db, config)
        if not account:
            return jsonify(error="Sign in to continue."), 401
        subject, _, csrf = account
        demo = cast("Demo | None", app.config.get("REWIND_DEMO"))
        if request.method == "GET":
            if operation == "session":
                return jsonify(token=csrf)
            if operation == "runs":
                page = request.args.get("page", 1, type=int)
                if not 1 <= page <= 10000:
                    return jsonify(error="Invalid library page."), 400
                rows = db.execute(
                    """SELECT id, summary, created_at, demo FROM rewind_recording
                       WHERE owner = %s OR demo ORDER BY created_at DESC, id DESC
                       LIMIT 51 OFFSET %s""",
                    (subject, (page - 1) * 50),
                ).fetchall()
                visible = rows[:50]
                linked = demo.links(db, subject, [row[0] for row in visible]) if demo else set()
                return jsonify(
                    runs=[
                        {
                            **summary,
                            "id": identifier.hex,
                            "created_at": created.isoformat(),
                            "demo": shared,
                            "has_source": identifier in linked,
                        }
                        for identifier, summary, created, shared in visible
                    ],
                    more=len(rows) > 50,
                )
            if operation.startswith("runs/") and (row := recording(db, subject, operation[5:])):
                return jsonify(run=asdict(parse_envelope(row[0])))
            if demo and (response := demo.get(db, subject, operation)) is not None:
                return response
        elif (
            request.headers.get("Origin") != config.origin
            or request.headers.get("X-Rewind-Token") != csrf
        ):
            return jsonify(error="Refresh the workspace and try again."), 403
        elif operation in {"import", "compare", "export"}:
            data = request.get_json()
            if not isinstance(data, dict):
                return jsonify(error="Expected a JSON object."), 400
            if operation == "import":
                try:
                    identifier = save_recording(db, data.get("recording"), subject)
                except (ValueError, OverflowError, RecursionError, Divergence) as exc:
                    app.logger.info("request=%s import=invalid", g.rewind_id)
                    message = str(exc)
                    if message not in {
                        "unsupported recording format",
                        "recording checksum mismatch",
                        "This bundle exceeds the hosted limit. Open it in local Rewind.",
                    }:
                        message = "Invalid recording structure or integrity. Export a valid Rewind bundle."
                    return jsonify(error=message), 400
                return jsonify(run_id=identifier), 201
            if operation == "export" and (row := recording(db, subject, data.get("run_id"))):
                return jsonify(row[0])
            if operation == "compare":
                left = recording(db, subject, data.get("left"))
                right = recording(db, subject, data.get("right"))
                if left and right:
                    runs = [parse_envelope(left[0]), parse_envelope(right[0])]
                    if any(len(run.boundaries) > COMPARE_LIMIT for run in runs):
                        return jsonify(
                            error="Too many steps for hosted comparison. Compare locally."
                        ), 413
                    result = jsonify(comparison=diagnose(runs[0], runs[1]))
                    if (result.calculate_content_length() or 0) > 3_500_000:
                        return jsonify(
                            error="Comparison evidence is too large. Compare locally."
                        ), 413
                    return result
        elif demo and operation in {
            "capture",
            "verify",
            "cancel",
            "provider-check",
            "corpus-audit",
        }:
            return demo.post(db, subject, operation, request.get_json())
    return jsonify(error="Recording or route not found."), 404
