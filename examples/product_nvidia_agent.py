"""A real NVIDIA NIM agent for capture in the Rewind workspace."""

import os

import httpx

key = os.environ.get("NVIDIA_API_KEY", "")
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "messages": [
                {"role": "user", "content": "Explain record and replay in one short sentence."}
            ],
            "max_tokens": 256,
            "stream": False,
        },
    )
    response.raise_for_status()
    print(response.json()["choices"][0]["message"].get("content") or "No text returned")
