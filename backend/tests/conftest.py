import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_ADMIN_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "")
    monkeypatch.setenv("ENABLE_OPENAI_OFFICIAL_USAGE_SYNC", "false")
    monkeypatch.setenv("ENABLE_OPENROUTER_OFFICIAL_USAGE_SYNC", "false")
    monkeypatch.setenv("ENABLE_GOOGLE_BILLING_SYNC", "false")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "")
    monkeypatch.setenv("GOOGLE_BILLING_BIGQUERY_DATASET", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("VECTOR_STORE_PATH", str(tmp_path / "vector_memory"))
    monkeypatch.setenv("ARTIFACT_STORE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("PROJECT_STORE_PATH", str(tmp_path / "projects"))
    monkeypatch.setenv("RUN_STORE_PATH", str(tmp_path / "runs"))
    monkeypatch.setenv("APPROVAL_STORE_PATH", str(tmp_path / "approvals"))
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    monkeypatch.setenv("WORKSPACE_STORE_PATH", str(tmp_path / "workspaces"))
    monkeypatch.setenv("CURRENT_STATE_PATH", str(tmp_path / "current_state.txt"))
    monkeypatch.setenv("MAX_INPUT_TOKENS_PER_CALL", "4000")
    monkeypatch.setenv("MAX_OUTPUT_TOKENS_PER_CALL", "500")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "0.05")
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "0.25")

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    yield TestClient(app)
    get_settings.cache_clear()
