"""Settings. Everything that differs between laptop and Railway lives here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://mhs:mhs@localhost:5441/mhs"

    # --- models -------------------------------------------------------------
    # Verified 2026-10-14 against models.list plus one structured-output call each.
    # Re-check before changing: `.venv/bin/python scripts/check_models.py`.
    anthropic_api_key: str | None = None
    # One call per feed item, so price dominates here.
    extraction_model: str = "claude-haiku-5-5"  # verified 2026-10-14 (models.list + structured call)
    # Batches of signals against the 15 questions; over-inclusion is the failure to avoid.
    judge_model: str = "claude-sonnet-5-5"  # verified 2026-10-14
    # One call per week (the Lagebericht), and the thing the reader actually reads.
    digest_model: str = "claude-opus-5-5"  # verified 2026-10-14
    digest_fallback_model: str = "claude-sonnet-5-5"  # verified 2026-10-14
    # Guards a runaway bill on a bad feed day (and the 60-day first backfill).
    max_extractions_per_cycle: int = 600
    extraction_concurrency: int = 8

    # --- judge (the 15 monitoring questions) ---------------------------------
    judge_batch_size: int = 10
    # Founders below this regional relevance are not judged (vergleich/bund/freistaat excepted).
    judge_min_relevance: float = 0.3

    # --- weekly report (Lagebericht) -----------------------------------------
    report_weekday: str = "thu"
    report_hour_local: int = 18
    report_timezone: str = "Europe/Berlin"

    # --- self-updating sources (weekly suggestions) ---------------------------
    # Verified live 2026-10-14: claude-sonnet-5-5 + web_search_20260209 + output_config json_schema
    # in one call (29 s, 3 searches). Proposals are verified by fetching them; a pending
    # suggestion is re-verified and adopted after suggest_adopt_after_days unless declined.
    suggest_model: str = "claude-sonnet-5-5"  # verified 2026-10-14
    suggest_web_search_tool: str = "web_search_20260209"  # verified 2026-10-14
    suggest_max_candidates: int = 8
    suggest_web_search_max_uses: int = 8
    suggest_adopt_after_days: int = 7
    suggest_weekday: str = "mon"
    suggest_hour_local: int = 6  # report_timezone (Europe/Berlin)

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
    # A list page is a snapshot, not a stream; the first N links in document order are
    # the newest on every site checked. Caps what a nav-heavy page can inject per cycle.
    max_page_items: int = 40
    # Items published earlier than this on first sight are archive, not news. Undated
    # items (list pages) are kept — a missing date is not evidence of age.
    max_item_age_days: int = 60
    user_agent: str = "Mozilla/5.0 (compatible; MiesbachScanner/0.1; +https://pharosfutures.com)"
    # method=query: Google News RSS search; {q} is the URL-encoded query.
    query_url_template: str = "https://news.google.com/rss/search?q={q}+when:60d&hl=de&gl=DE&ceid=DE:de"
    # method=pdf: new PDFs per source per cycle, and how much of each is read.
    max_pdfs_per_source: int = 5
    max_pdf_bytes: int = 15_000_000
    max_pdf_pages: int = 12
    max_pdf_chars: int = 20_000
    # method=diff: the added/removed lines handed to extraction.
    max_diff_chars: int = 6000

    # --- data ---------------------------------------------------------------
    # Repo-relative by default; the Docker image sets DATA_DIR=/data.
    data_dir: str | None = None

    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return Path(__file__).resolve().parents[2] / "data"

    # --- app ----------------------------------------------------------------
    app_password: str = "change-me"  # production sets APP_PASSWORD
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
