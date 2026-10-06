"""Server-side auth: email/password + Google OAuth 2.0 + HttpOnly sessions."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

_DEMO = Path(__file__).resolve().parent
_ROOT = Path(__file__).resolve().parents[2]
USERS_DB = _DEMO / "data" / "users.db"
COOKIE = "rewind_session"
SESSION_DAYS = 7
REDIRECT_URI = "http://127.0.0.1:8765/auth/google/callback"
DEMO_PASSWORD = "Rewind@2026"
DEMO_ACCOUNTS = (
    {
        "name": "Aastha Tyagi",
        "email": "atyagi1_be24@thapar.edu",
        "role": "Presenter",
    },
    {
        "name": "Faculty reviewer",
        "email": "mam@thapar.edu",
        "role": "Reviewer",
    },
)


def load_dotenv() -> None:
    for path in (_ROOT / ".env", _DEMO / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip("'").strip('"')
            if key and not os.environ.get(key):
                os.environ[key] = val


def google_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def allow_skip() -> bool:
    return os.environ.get("AUTH_ALLOW_SKIP", "1").strip() not in {"0", "false", "no"}


def _conn() -> sqlite3.Connection:
    USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(USERS_DB)
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT,
            provider TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    db.commit()
    return db


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 120_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _digest = stored.split("$", 1)
    return hmac.compare_digest(stored, _hash_password(password, salt))


def _user_public(row: sqlite3.Row) -> dict[str, Any]:
    return {"email": row["email"], "name": row["name"], "provider": row["provider"]}


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + SESSION_DAYS * 86400
    db = _conn()
    try:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        db.execute(
            "INSERT INTO sessions(token, user_id, expires_at) VALUES (?,?,?)",
            (token, user_id, expires),
        )
        db.commit()
    finally:
        db.close()
    return token


def destroy_session(token: str | None) -> None:
    if not token:
        return
    db = _conn()
    try:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
    finally:
        db.close()


def user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    db = _conn()
    try:
        row = db.execute(
            """
            SELECT u.email, u.name, u.provider
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, int(time.time())),
        ).fetchone()
        return _user_public(row) if row else None
    finally:
        db.close()


def register_email(name: str, email: str, password: str) -> tuple[int, dict[str, Any]] | str:
    name, email = name.strip(), email.strip().lower()
    if len(name) < 2:
        return "Enter your full name."
    if "@" not in email or "." not in email.split("@")[-1]:
        return "Enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    db = _conn()
    try:
        if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            return "An account with this email already exists. Sign in instead."
        db.execute(
            "INSERT INTO users(email, name, password_hash, provider, created_at) VALUES (?,?,?,?,?)",
            (email, name, _hash_password(password), "email", int(time.time())),
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        assert row is not None
        return int(row["id"]), _user_public(row)
    finally:
        db.close()


def login_email(email: str, password: str) -> tuple[int, dict[str, Any]] | str:
    email = email.strip().lower()
    db = _conn()
    try:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not row["password_hash"] or not _verify_password(password, row["password_hash"]):
            return "Email or password is incorrect."
        return int(row["id"]), _user_public(row)
    finally:
        db.close()


def ensure_demo_accounts() -> list[dict[str, str]]:
    """Upsert hashed local accounts so Sign in works for the mam demo."""
    db = _conn()
    issued: list[dict[str, str]] = []
    try:
        now = int(time.time())
        hashed = _hash_password(DEMO_PASSWORD)
        for account in DEMO_ACCOUNTS:
            email = account["email"].lower()
            row = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                db.execute(
                    "UPDATE users SET name = ?, password_hash = ?, provider = 'email' WHERE id = ?",
                    (account["name"], hashed, row["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO users(email, name, password_hash, provider, created_at) VALUES (?,?,?,?,?)",
                    (email, account["name"], hashed, "email", now),
                )
            issued.append(
                {
                    "role": account["role"],
                    "name": account["name"],
                    "email": email,
                    "password": DEMO_PASSWORD,
                }
            )
        db.commit()
    finally:
        db.close()
    return issued


def skip_guest() -> tuple[int, dict[str, Any]]:
    email = "mam@local.demo"
    db = _conn()
    try:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO users(email, name, password_hash, provider, created_at) VALUES (?,?,?,?,?)",
                (email, "Mam demo", None, "skip", int(time.time())),
            )
            db.commit()
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        assert row is not None
        return int(row["id"]), _user_public(row)
    finally:
        db.close()


def upsert_google_user(email: str, name: str) -> tuple[int, dict[str, Any]]:
    email = email.strip().lower()
    name = (name or email.split("@")[0]).strip() or "Google user"
    db = _conn()
    try:
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            db.execute(
                "UPDATE users SET name = ?, provider = CASE WHEN provider = 'email' THEN provider ELSE 'google' END WHERE id = ?",
                (name, row["id"]),
            )
            db.commit()
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        else:
            db.execute(
                "INSERT INTO users(email, name, password_hash, provider, created_at) VALUES (?,?,?,?,?)",
                (email, name, None, "google", int(time.time())),
            )
            db.commit()
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        assert row is not None
        return int(row["id"]), _user_public(row)
    finally:
        db.close()


_oauth_states: dict[str, float] = {}


def google_start_url() -> str | None:
    if not google_configured():
        return None
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = time.time() + 600
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def _httpx_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.request(method, url, **kwargs)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError:
        with httpx.Client(timeout=20.0, verify=False) as client:
            r = client.request(method, url, **kwargs)
            r.raise_for_status()
            return r.json()


def google_finish(code: str, state: str) -> tuple[int, dict[str, Any]] | str:
    if not google_configured():
        return "Google sign-in is not configured on the server."
    exp = _oauth_states.pop(state, 0)
    if exp < time.time():
        return "Google sign-in expired. Try again."
    try:
        tokens = _httpx_json(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
    except Exception as exc:  # noqa: BLE001
        return f"Google token exchange failed: {exc}"
    id_token = str(tokens.get("id_token") or "")
    if not id_token:
        return "Google did not return an ID token."
    try:
        info = _httpx_json(
            "GET",
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )
    except Exception as exc:  # noqa: BLE001
        return f"Google token verify failed: {exc}"
    if info.get("aud") != os.environ["GOOGLE_CLIENT_ID"]:
        return "Google token audience mismatch."
    if str(info.get("email_verified")).lower() not in {"true", "1"}:
        return "Google email is not verified."
    email = str(info.get("email") or "")
    if not email:
        return "Google account has no email."
    name = str(info.get("name") or info.get("given_name") or "")
    return upsert_google_user(email, name)


def session_cookie(token: str) -> str:
    return (
        f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}"
    )


def clear_cookie() -> str:
    return f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
