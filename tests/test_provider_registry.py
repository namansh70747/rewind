"""Active provider selection and credential routing."""

from urllib.parse import urlsplit

from flightrecorder.providers import PROVIDERS


def test_active_provider_registry() -> None:
    expected = {
        "groq": ("api.groq.com", "GROQ_API_KEY"),
        "gemini": ("generativelanguage.googleapis.com", "GEMINI_API_KEY"),
        "nvidia": ("integrate.api.nvidia.com", "NVIDIA_API_KEY"),
        "xai": ("api.x.ai", "XAI_API_KEY"),
    }
    assert set(PROVIDERS) == set(expected)
    for name, (host, credential) in expected.items():
        provider = PROVIDERS[name]
        assert urlsplit(provider.url).hostname == host
        assert urlsplit(provider.catalog_url).hostname == host
        assert provider.key_env == credential
