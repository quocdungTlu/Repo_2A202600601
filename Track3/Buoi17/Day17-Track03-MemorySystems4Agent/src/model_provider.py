from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider configuration shared by the agents.

    Supported providers for this lab:
    - openai
    - custom (OpenAI-compatible base URL)
    - gemini
    - anthropic
    - ollama
    - openrouter
    """

    provider: str
    model_name: str
    temperature: float
    api_key: str | None = None
    base_url: str | None = None


# Common typos / aliases mapped to canonical provider names.
_PROVIDER_ALIASES = {
    "openai": "openai",
    "oai": "openai",
    "custom": "custom",
    "openai-compatible": "custom",
    "gemini": "gemini",
    "google": "gemini",
    "google-genai": "gemini",
    "anthropic": "anthropic",
    "anthorpic": "anthropic",  # frequent typo
    "claude": "anthropic",
    "ollama": "ollama",
    "openrouter": "openrouter",
    "open-router": "openrouter",
}

SUPPORTED_PROVIDERS = ("openai", "custom", "gemini", "anthropic", "ollama", "openrouter")

# Some OpenAI-compatible gateways (e.g. antco ai-gateway) block the default
# OpenAI SDK User-Agent. Sending a plain httpx UA avoids that block.
_FRIENDLY_UA = {"User-Agent": "python-httpx/0.27.0"}


def _friendly_http_client():
    """Return an httpx.Client with a non-blocked User-Agent, or None."""

    try:
        import httpx

        return httpx.Client(headers=_FRIENDLY_UA, timeout=60.0)
    except Exception:
        return None


def normalize_provider(value: str) -> str:
    """Map aliases like ``anthorpic`` -> ``anthropic`` to a canonical name."""

    key = (value or "").strip().lower()
    if key in _PROVIDER_ALIASES:
        return _PROVIDER_ALIASES[key]
    if key in SUPPORTED_PROVIDERS:
        return key
    # Unknown providers fall back to openai-compatible custom mode.
    return "custom"


def build_chat_model(config: ProviderConfig):
    """Instantiate the real chat model for the selected provider.

    Imports are done lazily so the lab can run fully offline (and pass tests
    / benchmarks) without any provider SDK installed. Only the provider that is
    actually selected needs its dependency present.
    """

    provider = normalize_provider(config.provider)

    if provider in ("openai", "custom"):
        from langchain_openai import ChatOpenAI

        kwargs: dict = {
            "model": config.model_name,
            "temperature": config.temperature,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if provider == "custom" and config.base_url:
            kwargs["base_url"] = config.base_url
            kwargs["timeout"] = 60
            client = _friendly_http_client()
            if client is not None:
                kwargs["http_client"] = client
        return ChatOpenAI(**kwargs)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model_name,
            temperature=config.temperature,
            google_api_key=config.api_key,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = {"model": config.model_name, "temperature": config.temperature}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOllama(**kwargs)

    if provider == "openrouter":
        # OpenRouter is OpenAI-compatible; reuse ChatOpenAI with its base URL.
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": config.model_name,
            "temperature": config.temperature,
            "api_key": config.api_key,
            "base_url": config.base_url or "https://openrouter.ai/api/v1",
        }
        client = _friendly_http_client()
        if client is not None:
            kwargs["http_client"] = client
        return ChatOpenAI(**kwargs)

    raise ValueError(f"Unsupported provider: {config.provider!r}")
