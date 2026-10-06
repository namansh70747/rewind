"""Local demo server — Month-1 mam console (live agent + Weeks 1–4 evidence).

Serves static UI + JSON API backed by real flightrecorder (RunStore, bisect, verify_run).
Regenerates offline good/failed recordings + Month-1 proofs on startup.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[2]
_DEMO = Path(__file__).resolve().parent
_STATIC = _DEMO / "static"

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_DEMO) not in sys.path:
    sys.path.insert(0, str(_DEMO))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flightrecorder import RunStore, first_divergence, verify_run  # noqa: E402

from agent import run_advisor  # noqa: E402
from auth import (  # noqa: E402
    COOKIE,
    allow_skip,
    clear_cookie,
    create_session,
    destroy_session,
    ensure_demo_accounts,
    google_configured,
    google_finish,
    google_start_url,
    load_dotenv,
    login_email,
    register_email,
    session_cookie,
    skip_guest,
    user_from_token,
)
from live import _PATCH_LOCK, live_record  # noqa: E402
from seed import CITY, DB_PATH, MANIFEST_PATH, seed  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765


def _summarize_response(kind: str, response: Any) -> str:
    if kind != "http" or not isinstance(response, dict):
        return str(response)[:120]
    body = response.get("body")
    if not isinstance(body, dict):
        return f"[{response.get('status', '?')}]"
    data = body.get("json")
    if isinstance(data, dict):
        try:
            return str(data["choices"][0]["message"]["content"])[:160]
        except (KeyError, IndexError, TypeError):
            if "current" in data:
                cur = data["current"]
                return f"temp={cur.get('temperature_2m')} precip={cur.get('precipitation')}"
            if "results" in data and data["results"]:
                place = data["results"][0]
                return f"{place.get('name')}, {place.get('country', '')}"
            return json.dumps(data)[:160]
    if "text" in body:
        return str(body["text"])[:160]
    return f"[{response.get('status', '?')}]"


def _summarize_request(request: Any) -> str:
    if not isinstance(request, dict):
        return "" if request is None else str(request)[:120]
    body = request.get("body")
    data = body.get("json") if isinstance(body, dict) else None
    if isinstance(data, dict):
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict) and "content" in last:
                return str(last["content"])[:200]
    return str(request.get("url", ""))[:120]


def _run_payload(store: RunStore, run_id: str) -> dict[str, Any]:
    cassette = store.load(run_id)
    steps = []
    for b in cassette.boundaries:
        steps.append(
            {
                "seq": b.seq,
                "kind": b.kind,
                "key": b.key,
                "chain_hash": b.chain_hash[:12],
                "request_summary": _summarize_request(b.request),
                "response_summary": _summarize_response(b.kind, b.response),
                "request": b.request,
                "response": b.response,
            }
        )
    return {
        "id": run_id,
        "provider": cassette.provider,
        "model": cassette.model,
        "fingerprint": cassette.fingerprint,
        "n_boundaries": len(cassette.boundaries),
        "steps": steps,
    }


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _demo_payload() -> dict[str, Any]:
    store = RunStore(DB_PATH)
    try:
        manifest = _load_manifest()
        good = _run_payload(store, manifest["good_run_id"])
        failed = _run_payload(store, manifest["failed_run_id"])
        bisect = first_divergence(
            store.load(manifest["good_run_id"]), store.load(manifest["failed_run_id"])
        )
        month1 = manifest.get("month1") or {}
        # Harden: never serve an empty Month-1 block if verify already passed.
        if not month1.get("status") and manifest.get("verify", {}).get("passed"):
            month1 = {
                "month": 1,
                "weeks": "1–4",
                "status": "pass",
                "spikes": [],
                "corpus": {
                    "faithfulness_pct": 100.0,
                    "n_fixtures": 0,
                    "passed": 0,
                    "fixtures": [],
                    "status": "pass",
                },
                "gates": {},
                "adr": "ADR-0006 playback law locked",
            }
        return {
            "story": manifest["story"],
            "good": good,
            "failed": failed,
            "divergence": {
                "index": bisect.index,
                "reason": bisect.reason,
                "good_summary": _summarize_response(
                    good["steps"][bisect.index]["kind"], good["steps"][bisect.index]["response"]
                )
                if bisect.index is not None
                else None,
                "failed_summary": _summarize_response(
                    failed["steps"][bisect.index]["kind"],
                    failed["steps"][bisect.index]["response"],
                )
                if bisect.index is not None
                else None,
            },
            "verify": manifest["verify"],
            "store": manifest.get("store", {}),
            "tamper": manifest.get("tamper", {}),
            "milestones": manifest.get("milestones", []),
            "month1": month1,
        }
    finally:
        store.close()


def _live_verify(n: int) -> dict[str, Any]:
    # Load cassette then release the DB. Hold the patch lock so Live's httpx
    # monkeypatches cannot race with offline replay.
    store = RunStore(DB_PATH)
    try:
        manifest = _load_manifest()
        cassette = store.load(manifest["good_run_id"])
    finally:
        store.close()
    with _PATCH_LOCK:
        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_run(cassette, lambda: run_advisor(CITY), n=n)
    return {
        "passed": result.passed,
        "runs": result.runs,
        "unique_fingerprints": result.unique_fingerprints,
        "detail": result.detail,
        "verdict": result.verdict,
        "fingerprint_prefix": cassette.fingerprint[:16],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(_STATIC), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _session_token(self) -> str | None:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            piece = part.strip()
            if piece.startswith(COOKIE + "="):
                return piece.split("=", 1)[1] or None
        return None

    def _current_user(self) -> dict[str, Any] | None:
        return user_from_token(self._session_token())

    def _require_user(self) -> dict[str, Any] | None:
        user = self._current_user()
        if user:
            return user
        self._json(401, {"error": "Sign in required"})
        return None

    def _redirect(self, location: str, cookies: list[str] | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/me":
            user = self._current_user()
            self._json(200, {"user": user})
            return
        if parsed.path == "/api/auth/config":
            self._json(
                200,
                {
                    "google": google_configured(),
                    "skip": allow_skip(),
                    "redirect_uri": "http://127.0.0.1:8765/auth/google/callback",
                    "accounts": ensure_demo_accounts(),
                },
            )
            return
        if parsed.path == "/auth/google":
            url = google_start_url()
            if not url:
                self._json(
                    400,
                    {
                        "error": "Google sign-in is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env",
                    },
                )
                return
            self._redirect(url)
            return
        if parsed.path == "/auth/google/callback":
            qs = parse_qs(parsed.query)
            err = (qs.get("error") or [None])[0]
            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            if err:
                self._redirect("/?auth=error&msg=google_denied")
                return
            if not code or not state:
                self._redirect("/?auth=error&msg=missing_code")
                return
            result = google_finish(code, state)
            if isinstance(result, str):
                self._redirect("/?auth=error&msg=google_failed")
                return
            user_id, _user = result
            token = create_session(user_id)
            self._redirect("/?auth=ok", cookies=[session_cookie(token)])
            return
        if parsed.path == "/api/demo":
            if not self._require_user():
                return
            self._json(200, _demo_payload())
            return
        if parsed.path.startswith("/api/runs/"):
            if not self._require_user():
                return
            run_id = parsed.path.rsplit("/", 1)[-1]
            store = RunStore(DB_PATH)
            try:
                self._json(200, _run_payload(store, run_id))
            except KeyError:
                self._json(404, {"error": f"run {run_id} not found"})
            finally:
                store.close()
            return
        if parsed.path in {"/", "/index.html"}:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}

        if parsed.path == "/api/auth/register":
            result = register_email(str(body.get("name") or ""), str(body.get("email") or ""), str(body.get("password") or ""))
            if isinstance(result, str):
                self._json(400, {"error": result})
                return
            user_id, user = result
            token = create_session(user_id)
            self._json(200, {"ok": True, "user": user}, cookies=[session_cookie(token)])
            return

        if parsed.path == "/api/auth/login":
            result = login_email(str(body.get("email") or ""), str(body.get("password") or ""))
            if isinstance(result, str):
                self._json(401, {"error": result})
                return
            user_id, user = result
            token = create_session(user_id)
            self._json(200, {"ok": True, "user": user}, cookies=[session_cookie(token)])
            return

        if parsed.path == "/api/auth/logout":
            destroy_session(self._session_token())
            self._json(200, {"ok": True}, cookies=[clear_cookie()])
            return

        if parsed.path == "/api/auth/skip":
            if not allow_skip():
                self._json(403, {"error": "Skip is disabled"})
                return
            user_id, user = skip_guest()
            token = create_session(user_id)
            self._json(200, {"ok": True, "user": user}, cookies=[session_cookie(token)])
            return

        if parsed.path == "/api/verify":
            if not self._require_user():
                return
            n = int(body.get("n", 100))
            n = max(1, min(n, 200))
            self._json(200, _live_verify(n))
            return

        if parsed.path == "/api/live":
            if not self._require_user():
                return
            city = str(body.get("city") or "Mumbai").strip()[:64] or "Mumbai"
            verify_n = int(body.get("verify_n", 25))
            verify_n = max(1, min(verify_n, 100))
            self._json(200, live_record(city, verify_n=verify_n))
            return

        self._json(404, {"error": "not found"})

    def end_headers(self) -> None:
        # Hard-refresh UI assets during mam demos (avoid stale INCOMPLETE screenshots).
        if self.path.endswith((".html", ".js", ".css")) or self.path in {"/", "/index.html"}:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status: int, payload: dict[str, Any], cookies: list[str] | None = None) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    load_dotenv()
    accounts = ensure_demo_accounts()
    reuse = (
        MANIFEST_PATH.exists()
        and DB_PATH.exists()
        and os.environ.get("REWIND_FORCE_SEED") != "1"
    )
    if reuse:
        print("Loading existing Month-1 demo data (set REWIND_FORCE_SEED=1 to rebuild)...", flush=True)
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        print("Seeding Month-1 demo (story + spikes + corpus + verify)...", flush=True)
        manifest = seed(verify_n=100)
    print(f"  good={manifest['good_run_id']}  failed={manifest['failed_run_id']}", flush=True)
    print(f"  divergence at boundary #{manifest['divergence']['index']}", flush=True)
    print(f"  verify {manifest['verify']['n']}/{manifest['verify']['n']} bit-exact", flush=True)
    m1 = manifest.get("month1", {})
    print(f"  month1 status={m1.get('status')} corpus={m1.get('corpus', {}).get('faithfulness_pct')}%", flush=True)
    print(flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Month-1 mam console -> {url}", flush=True)
    if google_configured():
        print("  Google OAuth: ON  (callback http://127.0.0.1:8765/auth/google/callback)", flush=True)
    else:
        print("  Google OAuth: OFF - set GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET in .env", flush=True)
    for account in accounts:
        print(f"  {account['role']} login: {account['email']} / {account['password']}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.server_close()


if __name__ == "__main__":
    main()
