"""A real Gemini agent for capture in the Rewind workspace."""

import os

import httpx

key = os.environ.get("GEMINI_API_KEY", "")
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"parts": [{"text": "Explain record and replay in one short sentence."}]}]
        },
    )
    response.raise_for_status()
    print(response.json()["candidates"][0]["content"]["parts"][0]["text"])
