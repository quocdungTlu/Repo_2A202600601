from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the lab.

    - Paths for the repo root, dataset directory, and state directory.
    - Compact-memory settings (threshold + messages kept after compaction).
    - Provider settings for the main model and the judge model.
    """

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def _load_dotenv(root: Path) -> None:
    """Best-effort load of a ``.env`` file without a hard dependency."""

    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(root / ".env")
    except Exception:
        # python-dotenv not installed or no .env present -> rely on os.environ.
        pass


def _provider_from_env() -> ProviderConfig:
    """Build the main model provider config from environment variables."""

    provider = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    api_key = None
    base_url = None
    if provider in ("openai", "custom"):
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
        base_url = os.getenv("CUSTOM_BASE_URL")
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    elif provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    return ProviderConfig(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )


def _judge_from_env(main: ProviderConfig) -> ProviderConfig:
    """Judge model defaults to the main provider but can be overridden."""

    judge_model = os.getenv("JUDGE_MODEL", main.model_name)
    return ProviderConfig(
        provider=main.provider,
        model_name=judge_model,
        temperature=0.0,
        api_key=main.api_key,
        base_url=main.base_url,
    )


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables and return a populated ``LabConfig``."""

    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()
    _load_dotenv(root)

    data_dir = root / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    compact_threshold = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "600"))
    compact_keep = int(os.getenv("COMPACT_KEEP_MESSAGES", "6"))

    model = _provider_from_env()
    judge_model = _judge_from_env(model)

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold,
        compact_keep_messages=compact_keep,
        model=model,
        judge_model=judge_model,
    )
