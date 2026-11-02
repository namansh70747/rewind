"""Stream a real Groq tool call for capture and offline replay."""

import json
import os

import httpx

with (
    httpx.Client(timeout=120, trust_env=False) as client,
    client.stream(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer " + os.environ.get("GROQ_API_KEY", "")},
        json={
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "Use the lookup_weather tool for Delhi."}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "description": "Look up weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
            "tool_choice": "required",
            "max_completion_tokens": 512,
            "stream": True,
        },
    ) as response,
):
    response.raise_for_status()
    tool_seen = False
    done = False
    for line in response.iter_lines():
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                done = True
            else:
                event = json.loads(data)
                for choice in event.get("choices", []):
                    tool_seen = tool_seen or bool(choice.get("delta", {}).get("tool_calls"))
    if not (tool_seen and done):
        raise ValueError("The stream did not contain a complete tool call")
    print("Stream completed; a tool call was observed. Tool execution is not performed.")
