from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app settings loaded from environment variables.

    The MVP defaults to mock mode so the dashboard works without API keys or
    paid model calls. Real provider keys can be added later without changing
    route or orchestration code.
    """

    app_env: str = "development"
    mock_mode: bool = True

    openai_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""

    ceo_model: str = "gpt-5.5"
    ceo_service_tier: str = "flex"
    model_selector_model: str = "gemini-3.5-flash"
    cheap_worker_model: str = "gpt-5.4-nano"
    cheap_search_worker_model: str = "gemini-3.1-flash-lite"

    database_url: str = "sqlite:///./thehivemind.db"
    vector_store_path: str = "./data/vector_memory"

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlite_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            configured = Path(self.database_url.replace("sqlite:///", "", 1))
            return configured if configured.is_absolute() else REPO_ROOT / configured
        return REPO_ROOT / "thehivemind.db"

    @property
    def vector_path(self) -> Path:
        configured = Path(self.vector_store_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured


@lru_cache
def get_settings() -> Settings:
    return Settings()
