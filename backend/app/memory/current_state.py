from app.core.config import get_settings


def get_current_state() -> str:
    STATE_PATH = get_settings().state_path
    if STATE_PATH.exists():
        return STATE_PATH.read_text(encoding="utf-8").strip()
    return "MVP scaffold active: mock orchestration, local SQLite run logs, and local memory placeholders."


def update_current_state(summary: str) -> None:
    STATE_PATH = get_settings().state_path
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(summary, encoding="utf-8")
