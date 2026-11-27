"""Network demo using the hosted API and a private execution supervisor."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import httpx
from flask import jsonify
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from werkzeug.serving import WSGIRequestHandler, make_server

from flightrecorder.corpus_audit import _scan
from flightrecorder.portable import envelope, parse_envelope
from flightrecorder.product.hosted import Config, app, configuration, connection, save_recording
from flightrecorder.providers import PROVIDERS
from flightrecorder.scripts import source_hash

if TYPE_CHECKING:
    from flask import Response
    from psycopg import Connection

SCRIPTS = {
    "release-ready": ("Release checklist · ready", "offline_ready.py"),
    "release-blocked": ("Release checklist · missing rollback plan", "offline_blocked.py"),
    "live-release": ("Live model · release explanation", "live_release.py"),
}
MAX_REPLAYS = 10
JOB_TIMEOUT = 45


@dataclass(frozen=True)
class Source:
    label: str
    path: Path
    digest: str


class Demo:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.directory = Path(__file__).resolve().parent / "demo_scripts"
        self.sources = {
            identifier: Source(label, self.directory / name, source_hash(self.directory / name))
            for identifier, (label, name) in SCRIPTS.items()
        }
        provider = os.getenv("REWIND_DEMO_PROVIDER", "groq")
        if provider not in PROVIDERS:
            raise ValueError("Choose a provider in the Rewind registry.")
        self.provider = PROVIDERS[provider]
        self.model = os.getenv("REWIND_DEMO_MODEL", self.provider.default_model).strip()
        if not self.model:
            raise ValueError("Configure a nonempty approved model.")
        self.closed = Event()
        self.thread = Thread(target=self._run, daemon=True, name="rewind-demo-worker")

    def migrate(self) -> None:
        with connection(self.config) as db:
            db.execute("SELECT pg_advisory_xact_lock(628315)")
            resource = files("flightrecorder.product")
            for script in ("hosted.sql", "demo_schema.sql"):
                db.execute(resource.joinpath(script).read_text(encoding="utf-8"))

    def start(self) -> None:
        with connection(self.config) as db:
            db.execute(
                """UPDATE rewind_demo_job SET status = 'failed', error = %s
                   WHERE status IN ('queued', 'running')""",
                ("The demo worker restarted. Start a new job to retry.",),
            )
        self.thread.start()

    def _run(self) -> None:
        while not self.closed.is_set():
            try:
                self._next()
            except Exception as exc:
                app.logger.warning("Demo worker error: %s", type(exc).__name__)
            self.closed.wait(0.5)

    def _next(self) -> None:
        with connection(self.config) as db:
            job = db.execute(
                """UPDATE rewind_demo_job SET status = 'running'
                   WHERE id = (SELECT id FROM rewind_demo_job WHERE status = 'queued'
                               ORDER BY created LIMIT 1 FOR UPDATE SKIP LOCKED)
                   RETURNING id, owner, action, source_id, source_digest, recording_id, replays"""
            ).fetchone()
            if not job:
                return
            identifier, owner, action, source_id, approved_digest, recording_id, replays = job
            stored = None
            if action == "verify":
                stored = db.execute(
                    "SELECT bundle FROM rewind_recording WHERE id = %s AND owner = %s",
                    (recording_id, owner),
                ).fetchone()

        try:
            source = self.sources[source_id]
            if source.digest != approved_digest:
                raise ValueError("Source changed since capture. Capture the approved script again.")
            if action == "verify" and not stored:
                raise ValueError("Recording source is unavailable.")
            result = self._execute(
                identifier, source, action, replays, stored[0] if stored else None
            )
            self._complete(job, result)
        except Exception as exc:
            message = str(exc) if type(exc) is ValueError else "Demo execution could not finish."
            with connection(self.config) as db:
                db.execute(
                    """UPDATE rewind_demo_job SET
                       status = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'failed' END,
                       error = CASE WHEN cancel_requested THEN NULL ELSE %s END
                       WHERE id = %s AND status = 'running'""",
                    (message[:180], identifier),
                )

    def _execute(
        self, identifier: UUID, source: Source, action: str, replays: int, bundle: Any
    ) -> dict[str, Any] | None:
        names = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG")
        env = {key: os.environ[key] for key in names if key in os.environ}
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        if source.path.name == "live_release.py":
            env["REWIND_DEMO_PROVIDER"] = self.provider.name
            env["REWIND_DEMO_MODEL"] = self.model
            if action == "capture" and (key := os.getenv(self.provider.key_env)):
                env[self.provider.key_env] = key
        payload: bytes | None = json.dumps(
            {
                "source": str(source.path),
                "source_digest": source.digest,
                "action": action,
                "replays": replays,
                "bundle": bundle,
            }
        ).encode()
        with subprocess.Popen(
            [sys.executable, "-m", "flightrecorder.product.demo_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=self.directory,
            env=env,
        ) as child:
            deadline = monotonic() + JOB_TIMEOUT
            try:
                while True:
                    if self.closed.is_set() or self._cancelled(identifier):
                        return None
                    if monotonic() >= deadline:
                        raise ValueError("Job timed out. Check provider availability and retry.")
                    try:
                        output, _ = child.communicate(payload, timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        payload = None
                response = json.loads(output)
                if not isinstance(response, dict):
                    raise ValueError("Invalid demo worker response.")
                if child.returncode:
                    error = response.get("error", "Demo execution failed.")
                    raise ValueError(error)
                return response
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()

    def _cancelled(self, identifier: UUID) -> bool:
        with connection(self.config) as db:
            row = db.execute(
                "SELECT cancel_requested FROM rewind_demo_job WHERE id = %s", (identifier,)
            ).fetchone()
        return not row or bool(row[0])

    def _complete(self, job: tuple[Any, ...], result: dict[str, Any] | None) -> None:
        identifier, owner, action, _, _, recording_id, _ = job
        with connection(self.config) as db:
            row = db.execute(
                "SELECT cancel_requested FROM rewind_demo_job WHERE id = %s FOR UPDATE",
                (identifier,),
            ).fetchone()
            if not row:
                return
            if row[0] or result is None:
                db.execute(
                    "UPDATE rewind_demo_job SET status = 'cancelled' WHERE id = %s", (identifier,)
                )
                return
            if action == "capture":
                bundle = result["bundle"]
                cassette = parse_envelope(bundle)
                recording_id = UUID(save_recording(db, bundle, owner))
                failure = cassette.metadata.get("script_error")
                result = {"run_id": recording_id.hex, "boundaries": len(cassette.boundaries)}
                if failure:
                    result["script_error"] = failure
            else:
                result = result["verification"]
                row = db.execute(
                    "SELECT bundle, summary FROM rewind_recording WHERE id = %s AND owner = %s",
                    (recording_id, owner),
                ).fetchone()
                if not row:
                    raise ValueError("Recording source is unavailable.")
                cassette = parse_envelope(row[0])
                verification = {
                    "passed": result["passed"],
                    "replays": result["runs"],
                    "checked_at": datetime.now(UTC).isoformat(),
                }
                cassette.metadata["verification"] = verification
                db.execute(
                    "UPDATE rewind_recording SET bundle = %s, summary = %s WHERE id = %s",
                    (
                        Jsonb(envelope(cassette)),
                        Jsonb({**row[1], "verification": verification}),
                        recording_id,
                    ),
                )
            db.execute(
                """UPDATE rewind_demo_job SET status = 'completed', recording_id = %s, result = %s
                   WHERE id = %s""",
                (recording_id, Jsonb(result), identifier),
            )

    def links(self, db: Connection[tuple[Any, ...]], subject: str, ids: list[UUID]) -> set[UUID]:
        rows = db.execute(
            """SELECT recording_id, source_id, source_digest FROM rewind_demo_job
               WHERE owner = %s AND action = 'capture' AND recording_id = ANY(%s)
               AND status = 'completed'""",
            (subject, ids),
        )
        return {
            rid
            for rid, key, digest in rows
            if key in self.sources and self.sources[key].digest == digest
        }

    def get(self, db: Connection[tuple[Any, ...]], subject: str, operation: str) -> Response | None:
        if operation == "scripts":
            return jsonify(
                root="Approved demo scripts",
                scripts=[
                    {"value": key, "label": source.label}
                    for key, source in self.sources.items()
                    if key != "live-release" or os.getenv(self.provider.key_env)
                ],
            )
        if operation == "providers":
            last = db.execute(
                """SELECT r.summary FROM rewind_demo_job j
                   JOIN rewind_recording r ON r.id = j.recording_id
                   WHERE j.owner = %s AND j.action = 'capture' AND j.source_id = 'live-release'
                   AND j.status = 'completed' ORDER BY j.created DESC LIMIT 1""",
                (subject,),
            ).fetchone()
            result = last[0] if last else {}
            return jsonify(
                providers=[
                    {
                        "name": provider.name,
                        "configured": bool(os.getenv(provider.key_env)),
                        "inference": (
                            "Last live capture reported an agent failure."
                            if result.get("script_failed")
                            else "Live inference passed in your last capture."
                        )
                        if result.get("display_provider") == provider.name
                        else None,
                        "model": self.model
                        if provider == self.provider
                        else provider.default_model,
                    }
                    for provider in PROVIDERS.values()
                ],
                notice="Catalogue checks measure access. Capture the live script to verify inference.",
            )
        if operation == "coverage":
            return jsonify(
                supported=["Approved scripts", "New httpx clients", "Decorated tools"],
                limitations=[
                    "One execution job at a time",
                    "Offline replay of matching sources",
                    f"At most {MAX_REPLAYS} replays per job",
                ],
                storage_bytes=0,
                month2="Hosted PostgreSQL demo workspace",
            )
        if operation == "jobs":
            rows = db.execute(
                """SELECT id, action, source_id, recording_id, status, result, error,
                          EXTRACT(EPOCH FROM created)::double precision
                   FROM rewind_demo_job WHERE owner = %s ORDER BY created DESC LIMIT 30""",
                (subject,),
            )
            return jsonify(
                jobs=[
                    {
                        "id": jid.hex,
                        "type": action,
                        "script": SCRIPTS.get(source, (source, ""))[0],
                        "recording_id": rid.hex if rid else None,
                        "status": status,
                        "result": result,
                        "error": error,
                        "created": created,
                    }
                    for jid, action, source, rid, status, result, error, created in rows
                ]
            )
        return None

    def post(
        self, db: Connection[tuple[Any, ...]], subject: str, operation: str, data: Any
    ) -> Response | tuple[Response, int]:
        if not isinstance(data, dict):
            return jsonify(error="Expected a JSON object."), 400
        if operation in {"capture", "verify"}:
            return self.enqueue(db, subject, operation, data)
        if operation == "cancel":
            row = db.execute(
                """UPDATE rewind_demo_job SET cancel_requested = true,
                   status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END
                   WHERE id = %s AND owner = %s AND status IN ('queued', 'running')
                   RETURNING status""",
                (self._id(data.get("job_id")), subject),
            ).fetchone()
            return jsonify(status=row[0]) if row else (jsonify(error="Active job not found."), 404)
        if operation == "provider-check":
            provider = PROVIDERS.get(str(data.get("provider")))
            if provider is None or not (key := os.getenv(provider.key_env)):
                return jsonify(error="Provider key is unavailable in the demo process."), 400
            try:
                with httpx.Client(
                    timeout=8,
                    trust_env=False,
                    follow_redirects=False,
                    verify=ssl.create_default_context(),
                ) as client:
                    response = client.get(
                        provider.catalog_url, headers=provider.catalog_headers(key)
                    )
            except httpx.HTTPError:
                return jsonify(ok=False, message="Could not reach the provider catalogue.")
            return jsonify(
                ok=response.is_success,
                status=response.status_code,
                message=f"Catalogue returned HTTP {response.status_code}. Inference is checked separately.",
            )
        if operation == "corpus-audit":
            return self.audit(db, subject)
        return jsonify(error="Route not found."), 404

    @staticmethod
    def _id(value: Any) -> UUID | None:
        try:
            return UUID(value)
        except (ValueError, TypeError, AttributeError):
            return None

    def enqueue(
        self, db: Connection[tuple[Any, ...]], subject: str, action: str, data: dict[str, Any]
    ) -> tuple[Response, int]:
        rid = None
        replays = 0
        if action == "capture":
            key = data.get("source")
            if (
                data.keys() - {"source", "trusted"}
                or data.get("trusted") is not True
                or not isinstance(key, str)
                or key not in self.sources
            ):
                return jsonify(error="Choose and confirm an approved demo script."), 400
            if key == "live-release" and not os.getenv(self.provider.key_env):
                return jsonify(error="The live model key is not configured."), 400
            if key == "live-release":
                db.execute("SELECT pg_advisory_xact_lock(628316)")
                recent = db.execute(
                    """SELECT count(*) FILTER (WHERE created > now() - interval '15 seconds'),
                              count(*) FROM rewind_demo_job WHERE action = 'capture'
                       AND source_id = 'live-release' AND created > now() - interval '1 hour'"""
                ).fetchone()
                if recent and recent[1] >= 10:
                    return jsonify(error="Demo live capture limit is 10 per hour."), 429
                if recent and recent[0]:
                    return jsonify(error="Wait 15 seconds between live model captures."), 429
        else:
            requested_replays = data.get("replays")
            if (
                data.keys() - {"run_id", "replays"}
                or type(requested_replays) is not int
                or not 1 <= requested_replays <= MAX_REPLAYS
            ):
                return jsonify(
                    error=f"Choose a recorded source and 1 to {MAX_REPLAYS} replays."
                ), 400
            replays = requested_replays
            rid = self._id(data.get("run_id"))
            row = db.execute(
                """SELECT source_id, source_digest FROM rewind_demo_job
                   WHERE action = 'capture' AND status = 'completed'
                   AND recording_id = %s AND owner = %s""",
                (rid, subject),
            ).fetchone()
            if not row:
                return jsonify(
                    error="No approved capture source is available for this recording."
                ), 404
            key, digest = row
            if key not in self.sources or self.sources[key].digest != digest:
                return jsonify(
                    error="Source changed since capture. Capture the approved script again."
                ), 409
        identifier = uuid4()
        try:
            with db.transaction():
                db.execute(
                    """INSERT INTO rewind_demo_job
                       (id, owner, action, source_id, source_digest, recording_id, replays, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'queued')""",
                    (identifier, subject, action, key, self.sources[key].digest, rid, replays),
                )
        except UniqueViolation:
            return jsonify(error="Another demo job is active. Try again when it completes."), 409
        return jsonify(job_id=identifier.hex), 202

    @staticmethod
    def audit(db: Connection[tuple[Any, ...]], subject: str) -> Response:
        runs = bad = flagged = boundaries = stream_errors = 0
        rows = db.execute(
            """SELECT bundle FROM rewind_recording WHERE owner = %s OR demo
               ORDER BY created_at DESC LIMIT 20""",
            (subject,),
        )
        for (bundle,) in rows:
            runs += 1
            try:
                cassette = parse_envelope(bundle)
            except Exception:
                bad += 1
                continue
            matched, invalid_stream = _scan(bundle)
            flagged += matched
            stream_errors += invalid_stream
            boundaries += len(cassette.boundaries)
        return jsonify(
            passed=not (bad or flagged or stream_errors),
            runs_scanned=runs,
            blobs_scanned=boundaries,
            integrity_failures=bad,
            runs_with_known_patterns=flagged,
            unreadable_blobs=0,
            blobs_with_invalid_stream_bytes=stream_errors,
            scope="Scanned up to 20 visible recordings for known patterns and integrity.",
        )


class PrivateRequestHandler(WSGIRequestHandler):
    """Keep OAuth query strings out of the server access log."""

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8870)
    parser.add_argument("--allow-open-signup", action="store_true")
    args = parser.parse_args()
    try:
        config = configuration()
        if config.open_signup and not args.allow_open_signup:
            raise ValueError("Open signup requires --allow-open-signup and a protected tunnel.")
        demo = Demo(config)
    except ValueError as exc:
        parser.error(str(exc))
    server = make_server(
        "127.0.0.1", args.port, app, threaded=True, request_handler=PrivateRequestHandler
    )
    try:
        demo.migrate()
        demo.start()
        app.config["REWIND_DEMO"] = demo
        print(f"Rewind demo listening on 127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
    finally:
        demo.closed.set()
        if demo.thread.is_alive():
            demo.thread.join(timeout=8)
        server.server_close()


if __name__ == "__main__":
    main()
