from pathlib import Path
from functools import lru_cache

from fastapi import HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Central app settings loaded from environment variables.

    The MVP defaults to mock mode so the dashboard works without API keys or
    paid model calls. Real provider keys can be added later without changing
    route or orchestration code.
    """

    app_env: str = "development"
    mock_mode: bool = True
    allow_live_calls: bool = False

    openai_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""

    ceo_model: str = "gpt-5.5"
    ceo_service_tier: str = "flex"
    model_selector_model: str = "gemini-3.5-flash"
    cheap_worker_model: str = "gpt-5.4-nano"
    cheap_search_worker_model: str = "gemini-3.1-flash-lite"
    openrouter_default_model: str = "qwen/qwen3-coder"

    database_url: str = "sqlite:///./thehivemind.db"
    vector_store_path: str = "./data/vector_memory"
    artifact_store_path: str = "./backend/data/artifacts"
    workspace_store_path: str = "./backend/data/workspaces"
    project_store_path: str = "./backend/data/projects"
    run_store_path: str = "./backend/data/runs"
    current_state_path: str = "./backend/data/current_state.txt"
    openai_tracking_id: str = ""

    max_input_tokens_per_call: int = 4000
    max_output_tokens_per_call: int = 500
    max_cost_per_call_usd: float = 0.05
    max_cost_per_run_usd: float = 0.25
    monthly_ai_budget_usd: float = 10.00
    daily_ai_budget_usd: float = 1.00
    warning_budget_percent: float = 70
    danger_budget_percent: float = 90

    enable_openai_web_search: bool = False
    enable_gemini_grounding: bool = False
    enable_openrouter_search: bool = False

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

    @property
    def artifact_path(self) -> Path:
        configured = Path(self.artifact_store_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured

    @property
    def workspace_path(self) -> Path:
        configured = Path(self.workspace_store_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured

    @property
    def project_path(self) -> Path:
        configured = Path(self.project_store_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured

    @property
    def run_path(self) -> Path:
        configured = Path(self.run_store_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured

    @property
    def state_path(self) -> Path:
        configured = Path(self.current_state_path)
        return configured if configured.is_absolute() else REPO_ROOT / configured

    def is_live_allowed(self) -> bool:
        return self.allow_live_calls is True

    def require_live_allowed(self) -> None:
        if not self.is_live_allowed():
            raise HTTPException(
                status_code=403,
                detail="Live provider calls are disabled. Set ALLOW_LIVE_CALLS=true to enable controlled tests.",
            )

    def get_provider_key(self, provider: str) -> str:
        normalized = provider.lower()
        keys = {
            "openai": self.openai_api_key,
            "gemini": self.google_api_key,
            "openrouter": self.openrouter_api_key,
        }
        if normalized not in keys:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        return keys[normalized]

    def validate_provider_ready(self, provider: str) -> None:
        self.require_live_allowed()
        if not self.get_provider_key(provider):
            raise HTTPException(status_code=400, detail=f"{provider} API key is not configured.")


def is_live_allowed() -> bool:
    return get_settings().is_live_allowed()


def require_live_allowed() -> None:
    get_settings().require_live_allowed()


def get_provider_key(provider: str) -> str:
    return get_settings().get_provider_key(provider)


def validate_provider_ready(provider: str) -> None:
    get_settings().validate_provider_ready(provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
