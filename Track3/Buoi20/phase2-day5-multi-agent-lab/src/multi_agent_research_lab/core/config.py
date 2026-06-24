"""Application configuration.

Keep config small and explicit. Do not read environment variables directly in agents.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")

    langsmith_api_key: str | None = Field(default=None, validation_alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="multi-agent-research-lab", validation_alias="LANGSMITH_PROJECT")

    tavily_api_key: str | None = Field(default=None, validation_alias="TAVILY_API_KEY")

    max_iterations: int = Field(default=6, ge=1, le=20, validation_alias="MAX_ITERATIONS")
    timeout_seconds: int = Field(default=60, ge=5, le=600, validation_alias="TIMEOUT_SECONDS")

    # When True (or when no provider key is present) the LLM/search clients run in a
    # deterministic offline mock mode so the lab is reproducible without API credits.
    offline_mode: bool = Field(default=True, validation_alias="OFFLINE_MODE")

    # Rough price per 1K tokens (USD), used to estimate cost during benchmarking.
    price_per_1k_input: float = Field(default=0.00015, validation_alias="PRICE_PER_1K_INPUT")
    price_per_1k_output: float = Field(default=0.00060, validation_alias="PRICE_PER_1K_OUTPUT")

    llm_max_retries: int = Field(default=2, ge=0, le=10, validation_alias="LLM_MAX_RETRIES")

    @property
    def use_mock_llm(self) -> bool:
        """Mock unless explicitly online AND a provider key is configured."""

        return self.offline_mode or not self.openai_api_key

    @property
    def use_mock_search(self) -> bool:
        return self.offline_mode or not self.tavily_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
