"""Seed good + failed recordings for the Week-2 mam demo (offline, no API key).

Both runs share identical geocode + weather HTTP (same LLM *request*). The failed run
diverges only at the LLM *response* — so ``first_divergence`` reports:

    same input -> different output

at boundary #2 (the chat completion). Regenerated on every launch so nothing drifts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

# Allow `python demos/week2_mam/seed.py` from repo root without install.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from flightrecorder import RunStore, capture, first_divergence, verify_run  # noqa: E402

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
# Production failure label for the UI (wrong advice when precip is 0).
FAILURE_SUMMARY = (
    "Wrong umbrella advice: model warned of heavy rain while precipitation was 0.0 mm."
)


def _install_stub(llm_advice: str) -> None:
    """Patch httpx HTTPTransport so record needs no network."""

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


def _record(llm_advice: str, *, label: str, store: RunStore) -> str:
    _install_stub(llm_advice)
    with capture(store, provider="nvidia", model="meta/llama-3.1-8b-instruct") as cap:
        run_advisor(CITY)
    assert cap.run_id is not None and cap.cassette is not None
    kinds = [b.kind for b in cap.cassette.boundaries]
    assert kinds == ["http", "http", "http"], kinds
    # Stash a human label on the cassette via provider field already set; manifest holds story.
    _ = label
    return cap.run_id


def seed(*, verify_n: int = 100) -> dict[str, Any]:
    """Build DB + manifest. Returns the manifest dict."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for stale in DATA_DIR.glob("runs.db*"):
        stale.unlink(missing_ok=True)

    store = RunStore(DB_PATH)
    good_id = _record(GOOD_ADVICE, label="good", store=store)
    failed_id = _record(FAILED_ADVICE, label="failed", store=store)

    good = store.load(good_id)
    failed = store.load(failed_id)
    bisect = first_divergence(good, failed)
    assert bisect.diverged and bisect.index == 2, bisect
    assert "same input" in bisect.reason

    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        result = verify_run(good, lambda: run_advisor(CITY), n=verify_n)
    assert result.passed, result.detail
    assert result.unique_fingerprints == 1

    manifest = {
        "story": {
            "title": "Travel advisor — umbrella decision",
            "city": CITY,
            "task": (
                f"Geocode {CITY}, fetch live weather, ask the LLM whether to carry an umbrella."
            ),
            "failure_summary": FAILURE_SUMMARY,
            "good_advice": GOOD_ADVICE,
            "failed_advice": FAILED_ADVICE,
            "weather": WEATHER["current"],
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
            "fingerprint_prefix": good.fingerprint[:16],
        },
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
    print(f"manifest     : {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
