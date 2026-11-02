"""Single-user, loopback-only product API; trusted scripts execute in child processes."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx

from flightrecorder.diagnosis import diagnose
from flightrecorder.integrity import validate
from flightrecorder.portable import MAX_BYTES, envelope, import_run
from flightrecorder.store import RunStore


class ProductServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path, db: Path) -> None:
        super().__init__(address, Handler)
        self.root = root.resolve()
        self.db = db.resolve()
        self.token = secrets.token_urlsafe(32)
        self.jobs: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.lock = threading.Lock()
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS product_verification (run_id TEXT PRIMARY KEY, passed INTEGER NOT NULL, replays INTEGER NOT NULL, checked_at REAL NOT NULL)"
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
                        stderr=subprocess.DEVNULL,
                        text=True,
                        cwd=self.root,
                    )
                    self.processes[job_id] = process
                    self.jobs[job_id]["status"] = "running"
                output, _ = process.communicate(json.dumps(request), timeout=600)
                with self.lock:
                    if self.jobs[job_id]["status"] == "cancelled":
                        return
                    try:
                        result = json.loads(output.strip().splitlines()[-1])
                    except (ValueError, IndexError):
                        result = {
                            "ok": False,
                            "error": "Worker failed. Check the trusted script and environment.",
                        }
                    if (
                        action == "verify"
                        and result.get("ok")
                        and isinstance(result.get("result"), dict)
                    ):
                        verified = result["result"]
                        with sqlite3.connect(self.db) as conn:
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
                    self.jobs[job_id].update(
                        status="failed", error="Job exceeded the 10-minute limit."
                    )
            except Exception:
                with self.lock:
                    self.jobs[job_id].update(status="failed", error="Could not start job.")
            finally:
                with self.lock:
                    self.processes.pop(job_id, None)

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

    def do_GET(self) -> None:
        if not self._host_ok():
            self.send_error(403)
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path == "/":
            html = (
                files("flightrecorder.product").joinpath("index.html").read_text(encoding="utf-8")
            )
            payload = html.replace("__REWIND_TOKEN__", self.server.token).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        try:
            path = route.path
            if path == "/api/v1/runs":
                store = RunStore(self.server.db)
                try:
                    include_samples = urllib.parse.parse_qs(route.query).get("samples") == ["1"]
                    data = []
                    for run in store.list_runs():
                        cassette = store.load(run.id)
                        sample = run.provider == "demo" or bool(cassette.metadata.get("simulated"))
                        if include_samples or not sample:
                            check = store.conn.execute(
                                "SELECT passed, replays, checked_at FROM product_verification WHERE run_id = ?",
                                (run.id,),
                            ).fetchone()
                            verification = (
                                {
                                    "passed": bool(check[0]),
                                    "replays": check[1],
                                    "checked_at": check[2],
                                }
                                if check
                                else None
                            )
                            data.append(
                                {**asdict(run), "sample": sample, "verification": verification}
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
                                paths.append(str(file.relative_to(self.server.root)))
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
                            {"name": n, "configured": bool(os.getenv(k)), "model": m}
                            for n, k, m in [
                                ("NVIDIA", "NVIDIA_API_KEY", "nvidia/nemotron-3-super-120b-a12b"),
                                ("Gemini", "GEMINI_API_KEY", "gemini-2.5-flash"),
                            ]
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
                            "Selected time, random and UUID shims when enabled",
                        ],
                        "limitations": [
                            "No arbitrary subprocess or native network interception",
                            "No general filesystem capture",
                            "Socket guard is not an OS sandbox",
                            "Redaction is pattern based and incomplete",
                        ],
                        "month2": "Free-provider live evidence pending; original OpenAI and Anthropic gate remains separate.",
                    }
                )
            else:
                self._json({"error": "Not found"}, 404)
        except (KeyError, ValueError) as exc:
            self._json({"error": str(exc)}, 400)

    def do_POST(self) -> None:
        origin = self.headers.get("Origin")
        if (
            not self._host_ok()
            or (origin and origin != f"http://127.0.0.1:{self.server.server_port}")
            or not hmac.compare_digest(self.headers.get("X-Rewind-Token", ""), self.server.token)
        ):
            self._json({"error": "Unauthorized request"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BYTES:
                raise ValueError("Invalid request size.")
            body = json.loads(self.rfile.read(length))
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
                source = run.metadata.get("product_source")
                if not isinstance(source, str):
                    raise ValueError(
                        "This recording is not linked to a trusted source script. Imported recordings cannot execute code."
                    )
                replays = body.get("replays", 10)
                if type(replays) is not int or not 1 <= replays <= 100:
                    raise ValueError("Replay count must be between 1 and 100.")
                job = self.server.launch(
                    "verify", self.server.source(source), body["run_id"], replays
                )
                self._json({"job_id": job}, 202)
            elif path == "/api/v1/compare":
                self._json(
                    {
                        "comparison": diagnose(
                            self._load(body.get("left", "")), self._load(body.get("right", ""))
                        )
                    }
                )
            elif path == "/api/v1/export":
                cassette = self._load(body.get("run_id", ""))
                cassette.metadata.pop("product_source", None)
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
                    cassette.metadata.pop("product_source", None)
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
                provider = body.get("provider")
                if provider == "nvidia":
                    key, url, headers = (
                        os.getenv("NVIDIA_API_KEY", ""),
                        "https://integrate.api.nvidia.com/v1/models",
                        {},
                    )
                    headers = {"Authorization": f"Bearer {key}"}
                elif provider == "gemini":
                    key, url = (
                        os.getenv("GEMINI_API_KEY", ""),
                        "https://generativelanguage.googleapis.com/v1beta/models",
                    )
                    headers = {"x-goog-api-key": key}
                else:
                    raise ValueError("Unknown provider.")
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
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
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
