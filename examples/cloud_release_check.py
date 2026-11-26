"""Compare a local release manifest with Git, with one hosted model request."""

import json
import os
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
        limit: 128,
        "stream": False,
    }
    revision = git_head()
    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
        response = client.post(
            provider.url, headers=provider.headers(os.getenv(provider.key_env, "")), json=payload
        )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"].get("content")
    if not message:
        raise ValueError("Hosted model returned no visible release note")
    print(f"{provider_id}/{model}: {message.strip()}")

    manifest = read_release_manifest()
    if manifest["revision"] != revision:
        raise ValueError("Release manifest pins a different commit than the checkout")
    print("Release revision verified:", revision)


if __name__ == "__main__":
    main()
