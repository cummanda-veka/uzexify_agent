from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    postgres_password: str = ""
    database_url: str = "postgresql://uzex:CHANGE_ME@localhost:5432/uzex"
    agent_db_password: str = ""
    agent_database_url: str = "postgresql://uzex_agent:CHANGE_ME@localhost:5432/uzex"

    llm_base_url: str = "https://bifrost.coolthings.fyi/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "cpa-coolthings/gpt-6.1-terra"
    llm_fallback_model: str = "cpa-coolthings/claude-sonnet-5-5"
    llm_reasoning_effort: str = ""
    embedding_model: str = "google/gemini-embedding-2"
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""
    openrouter_api_key: str = ""

    agent_timeout_s: float = 75
    # Load protection (api/limits.py): questions per client per minute, concurrent agent runs,
    # and how long a question may wait for a free run before it is turned away.
    asks_per_minute: int = 12
    max_concurrent_asks: int = 8
    queue_wait_s: float = 20
    sql_timeout_ms: int = 10000
    sql_max_rows: int = 200
    company_match_min_score: float = 0.5
    cors_origins: str = "http://localhost:3000"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    telegram_bot_token: str = ""
    api_base_url: str = "http://localhost:8000"
    public_host: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
