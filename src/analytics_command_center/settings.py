"""Runtime settings. Secrets remain solely in environment variables."""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Make the conventional SDK environment variable available before an Agent is constructed.
# `override=False` preserves deployment-provided environment variables over a local .env.
load_dotenv(override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    openai_default_model: str = "gpt-5.6-terra"
    max_result_rows: int = 500
    query_timeout_seconds: float = 5.0
    max_sql_repairs: int = 1
    max_agent_turns: int = 8

    @property
    def live_agents_available(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
