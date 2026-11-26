"""Provider request shaping and the active hosted-provider registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Messages = list[dict[str, str]]


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    default_model: str
    key_env: str
    #: "openai" wire format (chat/completions + Bearer) or "anthropic" (messages + x-api-key)
    dialect: str = "openai"
    catalogue: str | None = None

    @property
    def catalog_url(self) -> str:
        return self.catalogue or self.url.removesuffix("/chat/completions") + "/models"

    def catalog_headers(self, api_key: str) -> dict[str, str]:
        if self.name == "gemini":
            return {"x-goog-api-key": api_key}
        return self.headers(api_key)

    def headers(self, api_key: str) -> dict[str, str]:
        if self.dialect == "anthropic":
            return {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        return {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}

    def body(self, model: str, messages: Messages) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "temperature": 0.7, "messages": messages}
        if self.dialect == "anthropic":
            payload["max_tokens"] = 64  # required by the Anthropic Messages API
        return payload

    def extract(self, data: Any) -> str:
        if self.dialect == "anthropic":
            return str(data["content"][0]["text"])
        return str(data["choices"][0]["message"]["content"])


OPENAI = Provider(
    name="openai",
    url="https://api.openai.com/v1/chat/completions",
    default_model="gpt-4o-mini",
    key_env="OPENAI_API_KEY",
)
NVIDIA = Provider(
    name="nvidia",
    url="https://integrate.api.nvidia.com/v1/chat/completions",
    default_model="nvidia/nemotron-3.5-bolt-e4b",
    key_env="NVIDIA_API_KEY",
)
ANTHROPIC = Provider(
    name="anthropic",
    url="https://api.anthropic.com/v1/messages",
    default_model="claude-haiku-4-5-20251001",
    key_env="ANTHROPIC_API_KEY",
    dialect="anthropic",
)

GEMINI = Provider(
    name="gemini",
    url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    default_model="gemini-3.5-flash-lite",
    key_env="GEMINI_API_KEY",
    catalogue="https://generativelanguage.googleapis.com/v1beta/models",
)

GROQ = Provider(
    name="groq",
    url="https://api.groq.com/openai/v1/chat/completions",
    default_model="openai/gpt-oss-20b",
    key_env="GROQ_API_KEY",
)
XAI = Provider(
    name="xai",
    url="https://api.x.ai/v1/chat/completions",
    default_model="grok-4",
    key_env="XAI_API_KEY",
)

PROVIDERS: dict[str, Provider] = {p.name: p for p in (GROQ, GEMINI, NVIDIA, XAI)}
# Historical built-in recordings still require their original request shape during replay.
REPLAY_PROVIDERS: dict[str, Provider] = {**PROVIDERS, "openai": OPENAI, "anthropic": ANTHROPIC}


def configured_secrets() -> tuple[str, ...]:
    import os

    return tuple(value for provider in PROVIDERS.values() if (value := os.getenv(provider.key_env)))
