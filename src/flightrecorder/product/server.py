"""Single-user, loopback-only product API; trusted scripts execute in child processes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from contextlib import closing
from dataclasses import asdict
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx

from flightrecorder.boundary import Divergence
from flightrecorder.diagnosis import diagnose
from flightrecorder.integrity import validate
from flightrecorder.portable import MAX_BYTES, envelope, import_run
from flightrecorder.provenance import check_source, digest
from flightrecorder.providers import PROVIDERS
from flightrecorder.store import RunStore, RunSummary


class ProductServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path, db: Path) -> None:
        super().__init__(address, Handler)
        self.root = root.resolve()
        self.db = db.resolve()
        self.token = secrets.token_urlsafe(32)
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        if bool(self.google_client_id) != bool(self.google_client_secret):
            raise ValueError("Google sign-in requires both OAuth client credentials.")
        self.google_pending: dict[str, tuple[float, str, str]] = {}
        self.google_subject: str | None = None
        self.sessions: dict[str, float] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.lock = threading.Lock()
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS product_verification (run_id TEXT PRIMARY KEY, passed INTEGER NOT NULL, replays INTEGER NOT NULL, checked_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS product_job_history "
                "(id TEXT PRIMARY KEY, created REAL NOT NULL, data TEXT NOT NULL)"
            )
            if self.google_client_id:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS product_google_account ("
                    "id INTEGER PRIMARY KEY CHECK (id = 1), subject TEXT NOT NULL)"
                )
                account = conn.execute(
                    "SELECT subject FROM product_google_account WHERE id = 1"
                ).fetchone()
                self.google_subject = account[0] if account else None
            for (data,) in conn.execute(
                "SELECT data FROM product_job_history ORDER BY created, id"
            ):
                job = json.loads(data)
                self.jobs[job["id"]] = job

    def save_job(self, job: dict[str, Any]) -> None:
        """Persist terminal job evidence and retain the 100 most recent jobs."""
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO product_job_history VALUES (?, ?, ?)",
                (job["id"], job["created"], json.dumps(job)),
            )
            conn.execute(
                "DELETE FROM product_job_history WHERE id IN ("
                "SELECT id FROM product_job_history ORDER BY created DESC, id DESC LIMIT -1 OFFSET 100)"
            )

    def source(self, value: str) -> Path:
        candidate = (self.root / value).resolve()
        if (
            not candidate.is_relative_to(self.root)
            or not candidate.is_file()
            or candidate.suffix != ".py"
        ):
            raise ValueError("Select an existing Python file inside the trusted workspace.")
        return candidate

    def launch(self, action: str, source: Path, run_id: str = "", replays: int = 10) -> str:
        job_id = secrets.token_hex(8)
        with self.lock:
            if any(j["status"] in ("queued", "running") for j in self.jobs.values()):
                raise ValueError("Another capture or verification is already running.")
            self.jobs[job_id] = {
                "id": job_id,
                "type": action,
                "status": "queued",
                "created": time.time(),
                "script": source.relative_to(self.root).as_posix(),
                "recording_id": run_id or None,
                "requested_replays": replays if action == "verify" else None,
            }

        def task() -> None:
            request = {
                "action": action,
                "source": str(source),
                "run_id": run_id,
                "replays": replays,
                "db": str(self.db),
            }
            try:
                with self.lock:
                    if self.jobs[job_id]["status"] == "cancelled":
                        return
                    process = subprocess.Popen(
                        [sys.executable, "-m", "flightrecorder.product.worker"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding="utf-8",
                        errors="replace",
                        cwd=self.root,
                        env={
                            key: value
                            for key, value in os.environ.items()
                            if key
                            not in {
                                "GOOGLE_CLIENT_ID",
                                "GOOGLE_CLIENT_SECRET",
                                "REWIND_GOOGLE_EMAIL",
                            }
                        },
                    )
                    self.processes[job_id] = process
                    self.jobs[job_id]["status"] = "running"
                output, stderr = process.communicate(json.dumps(request), timeout=600)
                with self.lock:
                    if self.jobs[job_id]["status"] == "cancelled":
                        return
                    try:
                        result = json.loads(output.strip().splitlines()[-1])
                        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                            raise ValueError("Invalid worker result")
                    except (ValueError, IndexError):
                        missing_module = (
                            "No module named 'flightrecorder'" in stderr
                            or "No module named flightrecorder" in stderr
                            or "No module named flightrecorder.product.worker" in stderr
                        )
                        result = {
                            "ok": False,
                            "error": (
                                "Rewind is missing from the worker's Python environment. Install Rewind in that environment and restart the workspace."
                                if missing_module
                                else f"Worker exited without a recording result (exit code {process.returncode}). Check the workspace Python dependencies and retry."
                            ),
                        }
                    if (
                        action == "verify"
                        and result.get("ok")
                        and isinstance(result.get("result"), dict)
                    ):
                        verified = result["result"]
                        with closing(sqlite3.connect(self.db)) as conn, conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO product_verification VALUES (?, ?, ?, ?)",
                                (
                                    run_id,
                                    int(bool(verified.get("passed"))),
                                    int(verified.get("runs", 0)),
                                    time.time(),
                                ),
                            )
                    self.jobs[job_id].update(
                        status="completed" if result.get("ok") else "failed", **result
                    )
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                with self.lock:
                    if self.jobs[job_id]["status"] != "cancelled":
                        self.jobs[job_id].update(
                            status="failed", error="Job exceeded the 10-minute limit."
                        )
            except Exception:
                with self.lock:
                    if self.jobs[job_id]["status"] != "cancelled":
                        self.jobs[job_id].update(
                            status="failed", error="Could not run the workspace job."
                        )
            finally:
                with self.lock:
                    self.processes.pop(job_id, None)
                    finished = dict(self.jobs[job_id])
                self.save_job(finished)

        threading.Thread(target=task, daemon=True).start()
        return job_id


class Handler(BaseHTTPRequestHandler):
    server: ProductServer

    def log_message(self, format: str, *args: Any) -> None:
        pass  # URLs and sensitive data must never be printed.

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        expected = f"127.0.0.1:{self.server.server_port}"
        return host == expected

    def _json(self, value: Any, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _load(self, run_id: str) -> Any:
        if len(run_id) != 12 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid recording ID.")
        store = RunStore(self.server.db)
        try:
            cassette = store.load(run_id)
            validate(cassette)
            return cassette
        finally:
            store.close()

    def _cookie(self, name: str) -> str:
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", "")).get(name)
        except CookieError:
            return ""
        return cookie.value if cookie else ""

    def _signed_in(self) -> bool:
        if not self.server.google_client_id:
            return True
        with self.server.lock:
            return self.server.sessions.get(self._cookie("rewind_session"), 0) > time.monotonic()

    def _redirect(self, target: str, *cookies: str) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _google(self, query: str, *, callback: bool) -> None:
        if not self.server.google_client_id:
            self.send_error(404)
            return
        redirect = f"http://127.0.0.1:{self.server.server_port}/auth/google/callback"
        if not callback:
            state, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(3))
            now = time.monotonic()
            with self.server.lock:
                self.server.google_pending = {
                    key: data for key, data in self.server.google_pending.items() if data[0] > now
                }
                self.server.google_pending[state] = (now + 600, verifier, nonce)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            params = urllib.parse.urlencode(
                {
                    "client_id": self.server.google_client_id,
                    "redirect_uri": redirect,
                    "scope": "openid email",
                    "response_type": "code",
                    "prompt": "select_account",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
            self._redirect(
                "https://accounts.google.com/o/oauth2/v2/auth?" + params,
                f"rewind_google_state={state}; Path=/auth/google; HttpOnly; SameSite=Lax; Max-Age=600",
            )
            return
        values = urllib.parse.parse_qs(query)
        state, code = (values.get(key, [""])[0] for key in ("state", "code"))
        clear_state = "rewind_google_state=; Path=/auth/google; HttpOnly; SameSite=Lax; Max-Age=0"
        with self.server.lock:
            pending = (
                self.server.google_pending.pop(state, None)
                if state == self._cookie("rewind_google_state")
                else None
            )
        if not pending or pending[0] <= time.monotonic() or not code:
            self._redirect("/?sign-in=failed", clear_state)
            return
        _, verifier, nonce = pending
        try:
            with httpx.Client(timeout=15, verify=ssl.create_default_context()) as client:
                tokens = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self.server.google_client_id,
                        "client_secret": self.server.google_client_secret,
                        "redirect_uri": redirect,
                        "code": code,
                        "code_verifier": verifier,
                        "grant_type": "authorization_code",
                    },
                )
                tokens.raise_for_status()
                identity = client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": tokens.json()["id_token"]},
                )
                identity.raise_for_status()
                claims = identity.json()
            # Tokeninfo validates the token with Google. Read the nonce from that same
            # validated token because the tokeninfo response can omit optional claims.
            payload = tokens.json()["id_token"].split(".")[1]
            token_claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            subject = claims["sub"]
            if (
                not isinstance(subject, str)
                or not subject
                or (
                    os.getenv("REWIND_GOOGLE_EMAIL")
                    and str(claims.get("email", "")).casefold()
                    != os.environ["REWIND_GOOGLE_EMAIL"].casefold()
                )
                or claims.get("aud") != self.server.google_client_id
                or claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
                or token_claims.get("nonce") != nonce
                or int(claims.get("exp", 0)) <= time.time()
                or str(claims.get("email_verified")).lower() != "true"
            ):
                raise ValueError("Invalid Google identity")
            session = secrets.token_urlsafe(32)
            now = time.monotonic()
            with self.server.lock:
                if self.server.google_subject not in {None, subject}:
                    raise ValueError("This workspace is linked to another account")
                if self.server.google_subject is None:
                    with closing(sqlite3.connect(self.server.db)) as conn, conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO product_google_account VALUES (1, ?)",
                            (subject,),
                        )
                        registered = conn.execute(
                            "SELECT subject FROM product_google_account WHERE id = 1"
                        ).fetchone()
                    if not registered or registered[0] != subject:
                        raise ValueError("This workspace is linked to another account")
                    self.server.google_subject = subject
                self.server.sessions = {
                    key: expiry for key, expiry in self.server.sessions.items() if expiry > now
                }
                self.server.sessions[session] = now + 28800
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, sqlite3.Error) as exc:
            print(
                "Google sign-in callback rejected:", type(exc).__name__, file=sys.stderr, flush=True
            )
            self._redirect("/?sign-in=failed", clear_state)
            return
        self._redirect(
            "/",
            clear_state,
            f"rewind_session={session}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800",
        )

    def do_GET(self) -> None:
        if not self._host_ok():
            self.send_error(403)
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path in {"/auth/google", "/auth/google/callback"}:
            self._google(route.query, callback=route.path.endswith("/callback"))
            return
        assets = {
            "/": ("index.html", "text/html"),
            "/workspace.css": ("workspace.css", "text/css"),
            "/workspace.js": ("workspace.js", "text/javascript"),
            "/rewind-mark.svg": ("rewind-mark.svg", "image/svg+xml"),
            "/rewind-mark.png": ("rewind-mark.png", "image/png"),
        }
        if route.path == "/" and not self._signed_in():
            assets["/"] = ("sign-in.html", "text/html")
        if asset := assets.get(route.path):
            filename, mime_type = asset
            resource = files("flightrecorder.product").joinpath(filename)
            if filename == "index.html":
                payload = (
                    resource.read_text(encoding="utf-8")
                    .replace("__REWIND_TOKEN__", self.server.token)
                    .replace(
                        "__REWIND_SIGN_OUT__", "" if self.server.google_client_id else "hidden"
                    )
                    .encode()
                )
            elif filename == "sign-in.html":
                failed = urllib.parse.parse_qs(route.query).get("sign-in") == ["failed"]
                payload = (
                    resource.read_text(encoding="utf-8")
                    .replace("__REWIND_SIGN_IN_ERROR__", "" if failed else "hidden")
                    .encode()
                )
            else:
                payload = resource.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                mime_type if mime_type.startswith("image/") else f"{mime_type}; charset=utf-8",
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if not self._signed_in():
            self._json({"error": "Sign in required"}, 401)
            return
        try:
            path = route.path
            if path == "/api/v1/session":
                self._json({"token": self.server.token})
            elif path == "/api/v1/runs":
                store = RunStore(self.server.db)
                try:
                    include_samples = urllib.parse.parse_qs(route.query).get("samples") == ["1"]
                    data = []
                    rows = store.conn.execute(
                        """SELECT r.id, r.provider, r.model, r.n_boundaries, r.created_at,
                                  r.fingerprint, m.data, v.passed, v.replays, v.checked_at
                           FROM run AS r
                           LEFT JOIN run_metadata AS m ON m.run_id = r.id
                           LEFT JOIN product_verification AS v ON v.run_id = r.id
                           ORDER BY r.created_at DESC"""
                    )
                    for row in rows:
                        run = RunSummary(*row[:6])
                        raw_metadata, passed, replays, checked_at = row[6:]
                        metadata = json.loads(raw_metadata) if raw_metadata is not None else {}
                        sample = run.provider == "demo" or bool(metadata.get("simulated"))
                        if include_samples or not sample:
                            verification = (
                                {
                                    "passed": bool(passed),
                                    "replays": replays,
                                    "checked_at": checked_at,
                                }
                                if passed is not None
                                else None
                            )
                            data.append(
                                {
                                    **asdict(run),
                                    "sample": sample,
                                    "verification": verification,
                                    "display_provider": metadata.get(
                                        "product_provider", run.provider
                                    ),
                                    "display_model": metadata.get("product_model", run.model),
                                    "has_source": isinstance(metadata.get("product_source"), str),
                                    "counterfactual": bool(metadata.get("counterfactual")),
                                    "script_failed": isinstance(metadata.get("script_error"), str),
                                }
                            )
                finally:
                    store.close()
                self._json({"runs": data})
            elif path.startswith("/api/v1/runs/"):
                self._json({"run": asdict(self._load(path.rsplit("/", 1)[-1]))})
            elif path == "/api/v1/scripts":
                excluded = {".git", ".venv", "node_modules", ".rewind", "__pycache__"}
                paths = []
                for current, dirs, names in os.walk(self.server.root):
                    dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
                    for name in names:
                        if name.endswith(".py"):
                            file = Path(current, name)
                            if file.resolve().is_relative_to(self.server.root):
                                paths.append(file.relative_to(self.server.root).as_posix())
                    if len(paths) >= 1000:
                        break
                self._json({"root": str(self.server.root), "scripts": sorted(paths)[:1000]})
            elif path == "/api/v1/jobs":
                with self.server.lock:
                    self._json({"jobs": list(self.server.jobs.values())[::-1]})
            elif path == "/api/v1/providers":
                self._json(
                    {
                        "providers": [
                            {
                                "name": p.name,
                                "configured": bool(os.getenv(p.key_env)),
                                "model": p.default_model,
                            }
                            for p in PROVIDERS.values()
                        ],
                        "notice": "Configured indicates environment presence only; live access and quota are not verified.",
                    }
                )
            elif path == "/api/v1/coverage":
                self._json(
                    {
                        "supported": [
                            "New httpx clients",
                            "Decorated tools",
                        ],
                        "limitations": [
                            "Browser capture leaves time, random and UUID shims off",
                            "No arbitrary subprocess or native network interception",
                            "No general filesystem capture",
                            "Socket guard is not an OS sandbox",
                            "Redaction is pattern based and incomplete",
                        ],
                        "storage_bytes": self.server.db.stat().st_size
                        if self.server.db.exists()
                        else 0,
                        "month2": "Live qualification is tracked separately for Groq, Gemini, NVIDIA and xAI.",
                    }
                )
            else:
                self._json({"error": "Not found"}, 404)
        except (KeyError, ValueError, Divergence) as exc:
            self._json({"error": str(exc)}, 400)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/auth/sign-out":
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if not self._host_ok() or self.headers.get("Origin") != expected:
                self._json({"error": "Unauthorized request"}, 403)
                return
            with self.server.lock:
                self.server.sessions.pop(self._cookie("rewind_session"), None)
            self._redirect("/", "rewind_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            return
        if not self._signed_in():
            self._json({"error": "Sign in required"}, 401)
            return
        origin = self.headers.get("Origin")
        if not self._host_ok() or (
            origin and origin != f"http://127.0.0.1:{self.server.server_port}"
        ):
            self._json({"error": "Unauthorized request"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BYTES:
                raise ValueError("Invalid request size.")
            raw_body = self.rfile.read(length)
            supplied_token = self.headers.get("X-Rewind-Token", "")
            if not supplied_token:
                self._json({"error": "Unauthorized request"}, 403)
                return
            if not hmac.compare_digest(supplied_token, self.server.token):
                self._json(
                    {
                        "error": "Workspace changed. Refresh the page and try again.",
                        "code": "stale_token",
                    },
                    409,
                )
                return
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/v1/capture":
                if body.get("trusted") is not True:
                    raise ValueError("Confirm that you trust this Python script before capture.")
                job = self.server.launch("capture", self.server.source(body.get("source", "")))
                self._json({"job_id": job}, 202)
            elif path == "/api/v1/verify":
                run = self._load(body.get("run_id", ""))
                if run.metadata.get("counterfactual"):
                    raise ValueError(
                        "Ordinary replay is unavailable for what-if forks. Inspect or compare the fork instead."
                    )
                source = run.metadata.get("product_source")
                if not isinstance(source, str):
                    raise ValueError(
                        "This recording is not linked to a trusted source script. Imported recordings cannot execute code."
                    )
                replays = body.get("replays", 10)
                if type(replays) is not int or not 1 <= replays <= 100:
                    raise ValueError("Replay count must be between 1 and 100.")
                alternative = body.get("source")
                if alternative is not None and (
                    not isinstance(alternative, str) or body.get("trusted") is not True
                ):
                    raise ValueError("Confirm that you trust the alternative Python script.")
                script = self.server.source(alternative if alternative is not None else source)
                if alternative is None and digest(script) != run.metadata.get("source_sha256"):
                    candidate = script.with_name(f"{script.stem}_legacy.py")
                    if candidate.is_file():
                        legacy = self.server.source(str(candidate))
                        if digest(legacy) == run.metadata.get("source_sha256"):
                            script = legacy
                try:
                    check_source(run.metadata, script)
                except ValueError:
                    self._json(
                        {
                            "error": "The script changed since capture. Choose the matching trusted source, or capture a new run with the current script.",
                            "code": "source_changed",
                        },
                        409,
                    )
                    return
                job = self.server.launch("verify", script, body["run_id"], replays)
                self._json({"job_id": job}, 202)
            elif path == "/api/v1/compare":
                self._json(
                    {
                        "comparison": diagnose(
                            self._load(body.get("left", "")), self._load(body.get("right", ""))
                        )
                    }
                )
            elif path == "/api/v1/corpus-audit":
                from flightrecorder.corpus_audit import audit_corpus

                self._json(audit_corpus(self.server.db))
            elif path == "/api/v1/export":
                cassette = self._load(body.get("run_id", ""))
                self._json(envelope(cassette))
            elif path == "/api/v1/import":
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".json", delete=False
                ) as temp:
                    temp.write(json.dumps(body.get("recording")))
                    temp_path = Path(temp.name)
                try:
                    cassette = import_run(temp_path)
                    store = RunStore(self.server.db)
                    try:
                        run_id = store.save(cassette)
                    finally:
                        store.close()
                finally:
                    temp_path.unlink(missing_ok=True)
                self._json({"run_id": run_id})
            elif path == "/api/v1/cancel":
                job_id = body.get("job_id", "")
                with self.server.lock:
                    if job_id not in self.server.jobs:
                        raise ValueError("Job not found.")
                    job_entry = self.server.jobs[job_id]
                    if job_entry["status"] not in ("queued", "running"):
                        raise ValueError("Job is no longer running.")
                    job_entry["status"] = "cancelled"
                    if job_id in self.server.processes:
                        self.server.processes[job_id].terminate()
                self._json({"status": "cancelled"})
            elif path == "/api/v1/provider-check":
                provider_id = body.get("provider")
                provider = PROVIDERS.get(provider_id) if isinstance(provider_id, str) else None
                if provider is None:
                    raise ValueError("Unknown provider.")
                key = os.getenv(provider.key_env, "")
                url = provider.catalog_url
                headers = provider.catalog_headers(key)
                if not key:
                    raise ValueError("Provider key is not configured in the server environment.")
                try:
                    response = httpx.get(url, headers=headers, timeout=15, follow_redirects=False)
                    self._json(
                        {
                            "ok": response.is_success,
                            "status": response.status_code,
                            "message": "Model catalogue access checked; inference and quota are not verified.",
                        }
                    )
                except httpx.HTTPError:
                    self._json(
                        {
                            "ok": False,
                            "message": "Provider connection failed; check your connection.",
                        }
                    )
            else:
                self._json({"error": "Not found"}, 404)
        except (ValueError, TypeError, KeyError, Divergence) as exc:
            self._json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Rewind's local product console")
    parser.add_argument(
        "--workspace", type=Path, default=Path.cwd(), help="trusted script workspace"
    )
    parser.add_argument("--db", type=Path, default=Path(".rewind/runs.db"))
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = ProductServer(("127.0.0.1", args.port), args.workspace, args.db)
    print(f"Rewind: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
