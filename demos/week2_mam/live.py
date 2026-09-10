"""Live agent capture for the mam demo.

Geocode + weather hit the real Open-Meteo network when TLS works. The LLM call uses
NVIDIA when ``NVIDIA_API_KEY`` is set; otherwise a local stub response is injected so
the demo still records three real-shaped HTTP boundaries without a paid key.

On Windows hosts with a broken CA store, we fall back to ``verify=False`` for the
Open-Meteo hop only after a probe fails — still a live network round-trip.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parents[2]
_DEMO = Path(__file__).resolve().parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_DEMO) not in sys.path:
    sys.path.insert(0, str(_DEMO))

from flightrecorder import RunStore, capture, verify_run  # noqa: E402

# ``flightrecorder.capture`` is shadowed by the exported ``capture`` function on the package.
capture_mod = sys.modules["flightrecorder.capture"]

from agent import LLM_URL, MODEL, run_advisor  # noqa: E402
from seed import DB_PATH  # noqa: E402

_ORIG_HANDLE = httpx.HTTPTransport.handle_request
_TRUE_CLIENT_INIT = httpx.Client.__init__
_CAPTURE_ORIG_CLIENT_INIT = capture_mod._orig_client_init


def _llm_stub_advice(city: str) -> str:
    return (
        f"Live Open-Meteo weather for {city} is recorded; "
        "umbrella advice served by the offline LLM stub (set NVIDIA_API_KEY for a live model)."
    )


def _probe_open_meteo() -> dict[str, Any]:
    """Return how to talk to Open-Meteo from this host."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    try:
        r = httpx.get(url, params={"name": "Mumbai", "count": 1}, timeout=15.0)
        r.raise_for_status()
        return {"ok": True, "verify": True, "mode": "live-tls"}
    except Exception as exc_tls:  # noqa: BLE001
        try:
            r = httpx.get(
                url, params={"name": "Mumbai", "count": 1}, timeout=15.0, verify=False
            )
            r.raise_for_status()
            return {
                "ok": True,
                "verify": False,
                "mode": "live-insecure-tls",
                "note": f"CA store probe failed ({exc_tls}); using verify=False for Open-Meteo",
            }
        except Exception as exc_insecure:  # noqa: BLE001
            return {
                "ok": False,
                "verify": True,
                "mode": "fixture-fallback",
                "error": f"live Open-Meteo unreachable: {exc_insecure}",
            }


def _install_hybrid_transport(
    city: str, *, use_live_llm: bool, network_mode: str
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        host = request.url.host or ""
        events.append({"event": "http", "host": host, "url": url[:120]})
        is_llm = "integrate.api.nvidia" in url or "openai.com" in url or "anthropic.com" in url
        if is_llm or url.startswith(LLM_URL[:32]):
            if use_live_llm:
                return _ORIG_HANDLE(self, request)
            body = {"choices": [{"message": {"content": _llm_stub_advice(city)}}]}
            events.append({"event": "llm_stub", "host": host})
            return httpx.Response(200, json=body, request=request)

        if network_mode == "fixture-fallback":
            if "geocoding" in url or "/search" in url:
                body = {
                    "results": [
                        {
                            "name": city,
                            "country": "Fixture",
                            "latitude": 19.076,
                            "longitude": 72.8777,
                        }
                    ]
                }
            elif "forecast" in url:
                body = {"current": {"temperature_2m": 27.8, "precipitation": 0.0}}
            else:
                body = {"ok": True}
            events.append({"event": "fixture", "host": host})
            return httpx.Response(200, json=body, request=request)

        events.append({"event": "live_network", "host": host})
        return _ORIG_HANDLE(self, request)

    httpx.HTTPTransport.handle_request = handle  # type: ignore[method-assign]
    return events


def _patch_client_verify(verify: bool) -> None:
    """Ensure capture()'s wrapped Client.__init__ still honors verify=False when needed."""
    if verify:
        capture_mod._orig_client_init = _CAPTURE_ORIG_CLIENT_INIT
        return

    def insecure_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("verify", False)
        _TRUE_CLIENT_INIT(self, *args, **kwargs)

    capture_mod._orig_client_init = insecure_init  # type: ignore[assignment]


def _restore_patches() -> None:
    httpx.HTTPTransport.handle_request = _ORIG_HANDLE  # type: ignore[method-assign]
    capture_mod._orig_client_init = _CAPTURE_ORIG_CLIENT_INIT
    httpx.Client.__init__ = _TRUE_CLIENT_INIT  # type: ignore[method-assign]


def live_record(
    city: str = "Mumbai",
    *,
    verify_n: int = 25,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Record one live-ish agent run, persist it, verify offline with kill-switch."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    use_live_llm = bool(os.environ.get("NVIDIA_API_KEY"))
    probe = _probe_open_meteo()
    network_mode = probe["mode"]
    _patch_client_verify(bool(probe.get("verify", True)))
    events = _install_hybrid_transport(city, use_live_llm=use_live_llm, network_mode=network_mode)

    store = RunStore(db_path)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            with capture(
                store,
                provider="nvidia" if use_live_llm else "live-hybrid",
                model=MODEL if use_live_llm else "stub-llm+open-meteo",
            ) as cap:
                advice = run_advisor(city)
    except Exception as exc:  # noqa: BLE001
        store.close()
        _restore_patches()
        return {
            "ok": False,
            "error": str(exc),
            "log": buf.getvalue(),
            "events": events,
            "live_llm": use_live_llm,
            "network_mode": network_mode,
            "city": city,
            "probe": probe,
        }

    assert cap.cassette is not None and cap.run_id is not None
    steps = [
        {
            "seq": b.seq,
            "kind": b.kind,
            "key": b.key,
            "chain_hash": b.chain_hash[:12],
        }
        for b in cap.cassette.boundaries
    ]

    # Verify must replay under the same LLM stub / fixture policy for non-recorded hosts.
    with contextlib.redirect_stdout(io.StringIO()):
        result = verify_run(cap.cassette, lambda: run_advisor(city), n=verify_n)

    payload = {
        "ok": True,
        "city": city,
        "advice": advice,
        "log": buf.getvalue().strip(),
        "live_weather": network_mode.startswith("live"),
        "live_llm": use_live_llm,
        "llm_mode": "nvidia" if use_live_llm else "stub",
        "network_mode": network_mode,
        "probe_note": probe.get("note") or probe.get("error"),
        "run_id": cap.run_id,
        "fingerprint": cap.cassette.fingerprint[:16],
        "n_boundaries": len(cap.cassette.boundaries),
        "steps": steps,
        "events": events,
        "verify": {
            "passed": result.passed,
            "n": result.runs,
            "unique_fingerprints": result.unique_fingerprints,
            "detail": result.detail,
            "kill_switch": True,
        },
        "cli": f"fr record -- python demos/week2_mam/agent.py {city}",
    }
    store.close()
    _restore_patches()
    return payload


if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "Mumbai"
    out = live_record(city, verify_n=10)
    print(out.get("log", ""))
    print(
        "ok=",
        out.get("ok"),
        "mode=",
        out.get("network_mode"),
        "run=",
        out.get("run_id"),
        "verify=",
        out.get("verify"),
    )
    if not out.get("ok"):
        print("error=", out.get("error"))
