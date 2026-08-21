"""LLM provider shaping — the only thing that differs between vendors.

Because capture is at the transport layer (ADR-0007), Rewind is provider-neutral: it just
needs to know how to shape a request and parse a response. OpenAI, NVIDIA (OpenAI-compatible
catalog) and Anthropic are supported out of the box.
"""

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
    default_model="meta/llama-3.1-8b-instruct",
    key_env="NVIDIA_API_KEY",
)
ANTHROPIC = Provider(
    name="anthropic",
    url="https://api.anthropic.com/v1/messages",
    default_model="claude-haiku-4-5-20251001",
    key_env="ANTHROPIC_API_KEY",
    dialect="anthropic",
)

PROVIDERS: dict[str, Provider] = {p.name: p for p in (OPENAI, NVIDIA, ANTHROPIC)}
