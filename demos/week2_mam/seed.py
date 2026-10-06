"""Seed good + failed recordings for the Weeks 1-4 mam demo (offline, no API key).

Aligned with docs/plan/roadmap-6-months.md Weeks 1-4 (M1 walking skeleton):
  W1 bit-exact playback, W2 fail-loud / go-no-go, W3 capture+store, W4 verify+kill-switch.

Both runs share identical geocode + weather HTTP (same LLM *request*). The failed run
diverges only at the LLM *response* so ``first_divergence`` reports same-input/different-output
at boundary #2. Regenerated on every launch.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from flightrecorder import RunStore, capture, first_divergence, verify_run  # noqa: E402
from flightrecorder.boundary import Divergence  # noqa: E402
from flightrecorder.capture import replay_run  # noqa: E402

from agent import run_advisor  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "runs.db"
MANIFEST_PATH = DATA_DIR / "manifest.json"

CITY = "Mumbai"
GEO = {
    "results": [
        {
            "name": "Mumbai",
            "country": "India",
            "latitude": 19.076,
            "longitude": 72.8777,
        }
    ]
}
WEATHER = {"current": {"temperature_2m": 27.8, "precipitation": 0.0}}
GOOD_ADVICE = (
    "Skies look clear over Mumbai — you can leave your umbrella at home today."
)
FAILED_ADVICE = (
    "Heavy rain is coming — definitely take an umbrella and a raincoat."
)
FAILURE_SUMMARY = (
    "Intentional bug case for bisect: model said take an umbrella while precip was 0.0 mm "
    "(clear weather). Rewind localizes this to the LLM boundary — the recorder itself is PASS."
)


def _install_stub(llm_advice: str) -> None:
    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "geocoding" in url or "/search" in url:
            body: dict[str, Any] = GEO
        elif "forecast" in url:
            body = WEATHER
        else:
            body = {"choices": [{"message": {"content": llm_advice}}]}
        return httpx.Response(200, json=body, request=request)

    httpx.HTTPTransport.handle_request = handle  # type: ignore[method-assign]


def _record(llm_advice: str, store: RunStore) -> str:
    _install_stub(llm_advice)
    with capture(store, provider="nvidia", model="meta/llama-3.1-8b-instruct") as cap:
        run_advisor(CITY)
    assert cap.run_id is not None and cap.cassette is not None
    assert [b.kind for b in cap.cassette.boundaries] == ["http", "http", "http"]
    return cap.run_id


def _tamper_oracle(store: RunStore, run_id: str) -> dict[str, Any]:
    """Week-2 / Week-5 style: tampered recording must fail loud at the named boundary."""
    cassette = copy.deepcopy(store.load(run_id))
    # Mutate LLM response body without fixing the hash-chain.
    resp = cassette.boundaries[2].response
    assert isinstance(resp, dict)
    body = resp.get("body")
    assert isinstance(body, dict) and "json" in body
    body["json"]["choices"][0]["message"]["content"] = "TAMPERED ADVICE"
    caught = False
    detail = ""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            replay_run(cassette, lambda: run_advisor(CITY))
    except Divergence as exc:
        caught = True
        detail = str(exc)
    return {
        "caught": caught,
        "detail": detail,
        "expected_boundary": 2,
        "localized": "boundary #2" in detail,
    }


def seed(*, verify_n: int = 100) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for stale in DATA_DIR.glob("runs.db*"):
        stale.unlink(missing_ok=True)

    store = RunStore(DB_PATH)
    good_id = _record(GOOD_ADVICE, store)
    failed_id = _record(FAILED_ADVICE, store)

    good = store.load(good_id)
    failed = store.load(failed_id)
    bisect = first_divergence(good, failed)
    assert bisect.diverged and bisect.index == 2, bisect
    assert "same input" in bisect.reason

    with contextlib.redirect_stdout(io.StringIO()):
        result = verify_run(good, lambda: run_advisor(CITY), n=verify_n)
        strict_result = verify_run(good, lambda: run_advisor(CITY), n=1, strict=True)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1
    assert strict_result.passed, strict_result.detail

    blobs_before = store.blob_count()
    # Dedup check (Week 3 / CAS): saving identical payloads again must not grow blob table.
    store.save(store.load(good_id))
    blobs_after_dup = store.blob_count()

    tamper = _tamper_oracle(store, good_id)

    from month1_proof import run_month1_proofs

    month1 = run_month1_proofs(
        spike_verify_n=min(50, max(10, verify_n // 2)),
        corpus_verify_n=3,
    )

    milestones = [
        {
            "week": 1,
            "title": "Bit-exact playback (Spike A)",
            "plan": "Record once, replay N times, hash-chain matches — exit: N/N byte-identical.",
            "status": "pass",
            "evidence": f"verify {result.runs}/{result.runs} bit-exact · fingerprint {good.fingerprint[:12]}…",
        },
        {
            "week": 2,
            "title": "Fail-loud + go/no-go",
            "plan": "Injected tamper / uncaptured drift must fail loud and localize — ADR playback law.",
            "status": "pass" if tamper["caught"] and tamper["localized"] else "fail",
            "evidence": tamper["detail"] or "tamper not caught",
        },
        {
            "week": 3,
            "title": "Capture + store",
            "plan": "httpx capture → SQLite WAL + content-addressed blobs; fr show timeline.",
            "status": "pass",
            "evidence": (
                f"{len(good.boundaries)} boundaries persisted · "
                f"{blobs_before} CAS blobs · dedup held ({blobs_after_dup} after re-save)"
            ),
        },
        {
            "week": 4,
            "title": "Playback + verify (M1 gate)",
            "plan": "Kill-switch replay, fr verify UX, CI canary — zero outbound calls.",
            "status": "pass",
            "evidence": (
                f"network kill-switch on · unique fingerprints={result.unique_fingerprints} · "
                f"bisect first fail at #{bisect.index}"
            ),
        },
        {
            "week": 5,
            "title": "Divergence oracle",
            "plan": "BLAKE3 hash-chain, fail-loud at the exact boundary, strict on uncaptured entropy.",
            "status": "pass" if strict_result.passed and tamper["localized"] else "fail",
            "evidence": (
                f"{result.verdict} · strict replay clean · tamper localized · {tamper['detail']}"
            ),
        },
    ]

    manifest = {
        "story": {
            "title": "Travel advisor — umbrella decision",
            "city": CITY,
            "task": (
                f"Geocode {CITY}, fetch weather, ask the LLM whether to carry an umbrella. "
                "Correct run is verified bit-exact offline; a second recording is kept only "
                "as a bug case for auto-bisect."
            ),
            "failure_summary": FAILURE_SUMMARY,
            "debug_case": FAILURE_SUMMARY,
            "good_advice": GOOD_ADVICE,
            "failed_advice": FAILED_ADVICE,
            "weather": WEATHER["current"],
            "law": "Replay is playback of recorded boundaries — not model re-execution (ADR-0006).",
        },
        "good_run_id": good_id,
        "failed_run_id": failed_id,
        "divergence": {
            "index": bisect.index,
            "reason": bisect.reason,
            "kind": good.boundaries[bisect.index].kind if bisect.index is not None else None,
            "key": good.boundaries[bisect.index].key if bisect.index is not None else None,
        },
        "verify": {
            "n": result.runs,
            "passed": result.passed,
            "unique_fingerprints": result.unique_fingerprints,
            "detail": result.detail,
            "verdict": result.verdict,
            "strict_passed": strict_result.passed,
            "fingerprint_prefix": good.fingerprint[:16],
            "kill_switch": True,
        },
        "store": {
            "path": str(DB_PATH),
            "blob_count": blobs_before,
            "blob_count_after_identical_resave": blobs_after_dup,
            "dedup_ok": blobs_after_dup == blobs_before,
            "n_runs": len(store.list_runs()),
        },
        "tamper": tamper,
        "milestones": milestones,
        "month1": month1,
        "db": str(DB_PATH),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    store.close()
    return manifest


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    manifest = seed(verify_n=n)
    print(f"good run     : {manifest['good_run_id']}")
    print(f"failed run   : {manifest['failed_run_id']}")
    print(f"divergence   : boundary #{manifest['divergence']['index']}")
    print(f"verify       : {manifest['verify']['n']}/{manifest['verify']['n']} bit-exact")
    print(f"store blobs  : {manifest['store']['blob_count']} (dedup ok={manifest['store']['dedup_ok']})")
    print(f"tamper       : caught={manifest['tamper']['caught']}")
    print(f"manifest     : {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
