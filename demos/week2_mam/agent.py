"""Travel-advisor agent for the Week-2 mam demo.

Unmodified style: plain httpx only — no flightrecorder imports. Three real-shaped
network steps: geocode city -> live weather -> LLM umbrella advice.
"""

from __future__ import annotations

import os
import ssl
import sys

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LLM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-bolt-e4b"


def run_advisor(city: str = "Mumbai") -> str:
    """Run the agent once; return the final advice line (also printed)."""
    with httpx.Client(timeout=30.0, verify=ssl.create_default_context()) as http:
        geo_resp = http.get(GEOCODE_URL, params={"name": city, "count": 1})
        geo_resp.raise_for_status()
        geo = geo_resp.json()
        results = geo.get("results") or []
        if not results:
            msg = f"Could not find a place called {city!r}."
            print(msg)
            return msg
        place = results[0]
        lat, lon = place["latitude"], place["longitude"]

        weather_resp = http.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,precipitation",
            },
        )
        weather_resp.raise_for_status()
        current = weather_resp.json()["current"]
        temp, precip = current["temperature_2m"], current["precipitation"]

        prompt = (
            f"Weather in {place['name']}, {place.get('country', '')}: {temp}C, "
            f"precipitation {precip} mm. In ONE friendly sentence, tell me whether "
            "to carry an umbrella today."
        )
        api_key = os.environ.get("NVIDIA_API_KEY", "replay-needs-no-key")
        answer_resp = http.post(
            LLM_URL,
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": os.getenv("REWIND_WEATHER_MODEL", MODEL),
                "max_tokens": 512,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        answer_resp.raise_for_status()
        content = answer_resp.json()["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("NVIDIA returned no visible weather advice")
        advice = content.strip()

    print(f"{place['name']}, {place.get('country', '')} — {temp}C, precip {precip} mm")
    print(advice)
    return advice


def main() -> None:
    city = sys.argv[1] if len(sys.argv) > 1 else "Mumbai"
    run_advisor(city)


if __name__ == "__main__":
    main()
