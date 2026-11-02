"""A real Groq agent for capture and offline replay in the Rewind workspace."""

import os

import httpx

key = os.environ.get("GROQ_API_KEY", "")
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={
            "model": "openai/gpt-oss-20b",
            "messages": [
                {
                    "role": "user",
                    "content": "Explain deterministic record and replay in one concise sentence.",
                }
            ],
            "max_completion_tokens": 256,
            "stream": False,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"].get("content")
    print(content or "No text returned")
