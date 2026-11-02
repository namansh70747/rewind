"""A real, unmodified tool-using agent — the kind Rewind records with zero code changes.

Given a city, it:
  1. geocodes the city name  → real public API (open-meteo, no key)
  2. fetches the live weather → real public API (open-meteo, no key)
  3. asks an LLM to turn that into one line of umbrella advice → real NVIDIA call

Three real network calls, genuine LLM sampling. Nothing here imports or knows about Rewind.
Run it directly:

    NVIDIA_API_KEY=... python examples/weather_agent.py "Delhi"

or record it (unchanged) and replay it bit-exact, offline:

    fr record --provider nvidia -- python examples/weather_agent.py "Delhi"
    fr verify <run> --n 50
"""

from __future__ import annotations

import os
import sys

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LLM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "meta/llama-3.1-8b-instruct"


def main() -> None:
    city = sys.argv[1] if len(sys.argv) > 1 else "Delhi"

    with httpx.Client(timeout=30.0) as http:
        geo_resp = http.get(GEOCODE_URL, params={"name": city, "count": 1})
        geo_resp.raise_for_status()
        geo = geo_resp.json()
        results = geo.get("results")
        if not results:
            print(f"Could not find a place called {city!r}.")
            return
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
        weather = weather_resp.json()
        current = weather["current"]
        temp, precip = current["temperature_2m"], current["precipitation"]

        prompt = (
            f"Weather in {place['name']}, {place.get('country', '')}: {temp}°C, "
            f"precipitation {precip} mm. In ONE friendly sentence, tell me whether "
            "to carry an umbrella today."
        )
        # The key is only needed to talk to the real API while recording; on replay the
        # response is served from the recording, so any placeholder value works.
        api_key = os.environ.get("NVIDIA_API_KEY", "replay-needs-no-key")
        answer_resp = http.post(
            LLM_URL,
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": MODEL,
                "temperature": 0.7,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        answer_resp.raise_for_status()
        answer = answer_resp.json()
        advice = answer["choices"][0]["message"]["content"].strip()

    print(f"\n{place['name']}, {place.get('country', '')} — {temp}°C, precip {precip} mm")
    print(f"{advice}\n")


if __name__ == "__main__":
    main()
