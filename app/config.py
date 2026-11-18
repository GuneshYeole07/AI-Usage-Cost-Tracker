"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "LLM Token Auditor"
    VERSION: str = "2.0.0"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "sqlite:///./ai_tracker.db"

    # --- Waste-rule thresholds (all tunable, all explainable) ---
    # Context size (tokens) after which every extra turn is treated as "chat ran too long".
    LONG_CONTEXT_THRESHOLD: int = 100_000
    # Floor for what a fresh session carries. The rule also never goes below the
    # session's own first message, because a new session restarts with the same setup.
    FRESH_SESSION_BASELINE: int = 20_000
    # Minimum avoidable tokens before a long-context finding is reported.
    LONG_CONTEXT_MIN_WASTE: int = 50_000
    # Consecutive failing tool turns that count as an agent loop.
    LOOP_MIN_CONSECUTIVE_ERRORS: int = 4
    # Retries we consider reasonable before a loop starts wasting tokens.
    LOOP_ALLOWED_RETRIES: int = 2
    # Reads of the same (unchanged) file allowed before re-reads count as waste.
    REREAD_ALLOWED: int = 2
    # First-turn context above this means too many tools / MCP servers / a bloated CLAUDE.md.
    # Calibrated on real Claude Code sessions (Nov 2026): the built-in prompt and tools
    # alone start around 45-55k tokens, so only the part above that is avoidable.
    TOOL_OVERHEAD_THRESHOLD: int = 65_000
    LEAN_STARTUP_CONTEXT: int = 50_000
    # A "small task" session: few turns, little output.
    SMALL_TASK_MAX_TURNS: int = 6
    SMALL_TASK_MAX_OUTPUT: int = 2_000
    # Cache efficiency: sessions this long should be mostly cache reads.
    CACHE_MIN_TURNS: int = 10
    CACHE_MIN_HIT_RATIO: float = 0.7

    # Team monthly token budget used for the forecast page.
    MONTHLY_TOKEN_BUDGET: int = 850_000_000

    BACKEND_API_URL: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
