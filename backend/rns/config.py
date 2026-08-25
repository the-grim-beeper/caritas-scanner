"""Settings. Everything that differs between laptop and Railway lives here."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://rns:rns@localhost:5438/rns"

    # --- models -------------------------------------------------------------
    anthropic_api_key: str | None = None
    # One call per feed item, so price dominates here.
    extraction_model: str = "claude-haiku-4-5"
    # One call per cycle, and the thing the reader actually reads.
    digest_model: str = "claude-opus-5"
    digest_fallback_model: str = "claude-sonnet-5"
    # Guards a runaway bill on a bad feed day rather than tuning throughput.
    max_extractions_per_cycle: int = 1500
    extraction_concurrency: int = 8

    # --- analysis -----------------------------------------------------------
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Cosine distance under which two signals are the same story from different
    # outlets. Derived from this corpus (scripts/derive_threshold.py); the
    # default is a starting point, not an inheritance from another project.
    story_threshold: float = 0.22
    story_window_days: int = 14

    # --- collection ---------------------------------------------------------
    feed_timeout_seconds: float = 20.0
    feed_concurrency: int = 12
    # Quarantined after this many consecutive failures; never deleted.
    max_consecutive_failures: int = 5
    user_agent: str = "Mozilla/5.0 (compatible; RheinNeckarScanner/0.1; +https://pharosfutures.com)"

    # --- app ----------------------------------------------------------------
    app_password: str = "kurpfalz"
    secret_key: str = "dev-only-change-me"
    session_max_age_seconds: int = 60 * 60 * 24 * 7
    cycle_hour_utc: int = 5
    scheduler_enabled: bool = True
    environment: str = "development"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
