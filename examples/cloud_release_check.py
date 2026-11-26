"""Compare a local release manifest with Git, with one hosted model request."""

import json
import os
import ssl
import subprocess
from pathlib import Path

import httpx

from flightrecorder import tool
from flightrecorder.providers import PROVIDERS


@tool(name="git_head", mutating=False)
def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


@tool(name="read_release_manifest", mutating=False)
def read_release_manifest() -> dict[str, str]:
    path = Path(os.getenv("REWIND_RELEASE_MANIFEST", ".rewind/release.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    provider_id = os.getenv("REWIND_CLOUD_PROVIDER", "groq")
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError("REWIND_CLOUD_PROVIDER must be groq, gemini, nvidia, or xai")
    model = os.getenv("REWIND_CLOUD_MODEL", provider.default_model)
    limit = "max_tokens" if provider_id == "nvidia" else "max_completion_tokens"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "In one short sentence, explain why a release manifest pins a Git commit.",
            }
        ],
        limit: 512,
        "stream": False,
    }
    if provider_id == "groq" and model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
        payload["reasoning_effort"] = "low"
    revision = git_head()
    with httpx.Client(
        timeout=30, trust_env=False, follow_redirects=False, verify=ssl.create_default_context()
    ) as client:
        response = client.post(
            provider.url, headers=provider.headers(os.getenv(provider.key_env, "")), json=payload
        )
    response.raise_for_status()
    choice = response.json()["choices"][0]
    message = choice["message"].get("content")
    if not isinstance(message, str) or not message.strip():
        if choice.get("finish_reason") == "length":
            raise ValueError(
                "Hosted model reached the completion token limit before producing a visible "
                "release note. Increase the completion limit or choose a different model."
            )
        raise ValueError(
            "Hosted model returned no visible release note "
            f"(finish reason: {choice.get('finish_reason') or 'unknown'})."
        )
    print(f"{provider_id}/{model}: {message.strip()}")

    manifest = read_release_manifest()
    if manifest["revision"] != revision:
        raise ValueError("Release manifest pins a different commit than the checkout")
    print("Release revision verified:", revision)


if __name__ == "__main__":
    main()
