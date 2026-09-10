"""Local demo server for the Week-2 mam timeline UI.

Serves static files + JSON API backed by real flightrecorder (RunStore, bisect, verify_run).
Regenerates the offline good/failed recordings on startup.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
_DEMO = Path(__file__).resolve().parent
_STATIC = _DEMO / "static"

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_DEMO) not in sys.path:
    sys.path.insert(0, str(_DEMO))

from flightrecorder import RunStore, first_divergence, verify_run  # noqa: E402

from agent import run_advisor  # noqa: E402
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
        }
    finally:
        store.close()


def _live_verify(n: int) -> dict[str, Any]:
    store = RunStore(DB_PATH)
    try:
        manifest = _load_manifest()
        cassette = store.load(manifest["good_run_id"])
        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_run(cassette, lambda: run_advisor(CITY), n=n)
        return {
            "passed": result.passed,
            "runs": result.runs,
            "unique_fingerprints": result.unique_fingerprints,
            "detail": result.detail,
            "fingerprint_prefix": cassette.fingerprint[:16],
        }
    finally:
        store.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(_STATIC), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/demo":
            self._json(200, _demo_payload())
            return
        if parsed.path.startswith("/api/runs/"):
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
        if parsed.path != "/api/verify":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        n = int(body.get("n", 100))
        n = max(1, min(n, 200))
        self._json(200, _live_verify(n))

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    print("Seeding good + failed runs (verify 100x)…")
    manifest = seed(verify_n=100)
    print(f"  good={manifest['good_run_id']}  failed={manifest['failed_run_id']}")
    print(f"  divergence at boundary #{manifest['divergence']['index']}")
    print(f"  verify {manifest['verify']['n']}/{manifest['verify']['n']} bit-exact")
    print()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Weeks 1-4 mam demo UI → {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        server.server_close()


if __name__ == "__main__":
    main()
