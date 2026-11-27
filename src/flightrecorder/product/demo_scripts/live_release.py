"""Make one bounded provider call with a fixed demonstration prompt."""

from __future__ import annotations

import os
import ssl

import httpx

from flightrecorder.providers import PROVIDERS


def main() -> None:
    provider = PROVIDERS[os.environ["REWIND_DEMO_PROVIDER"]]
    model = os.environ["REWIND_DEMO_MODEL"]
    body = provider.body(
        model,
        [{"role": "user", "content": "In one short sentence, explain a release rollback plan."}],
    )
    body["max_tokens" if provider.name == "nvidia" else "max_completion_tokens"] = 256
    if provider.name == "groq" and model.startswith("openai/gpt-oss-"):
        body["reasoning_effort"] = "low"
    with httpx.Client(
        timeout=20, trust_env=False, follow_redirects=False, verify=ssl.create_default_context()
    ) as client:
        response = client.post(
            provider.url,
            headers=provider.headers(os.environ.get(provider.key_env, "")),
            json=body,
        )
    problems = {
        401: "Provider credentials were rejected.",
        403: "Provider access was denied.",
        404: "Approved model is unavailable.",
        410: "Approved model was retired.",
        429: "Provider rate limit or quota reached.",
    }
    if not response.is_success:
        raise ValueError(problems.get(response.status_code, "Provider request failed."))
    message = provider.extract(response.json())
    if not message.strip():
        raise ValueError("Provider response contained no visible answer.")
    print(message.strip())


if __name__ == "__main__":
    main()
