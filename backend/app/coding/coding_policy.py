from __future__ import annotations

from pathlib import Path

from app.coding.schemas import AllowedUserFileScope, TaskType


PROTECTED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    "artifacts",
    "runs",
    "provider_usage",
    "approvals",
    "memory",
    "logs",
}

SECRET_NAMES = {
    ".env",
    "service-account.json",
    "service_account.json",
    "credentials.json",
    "token.json",
}

SECRET_SUFFIXES = {
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

SYSTEM_METADATA_NAMES = {
    "project_state.md",
    "manifest.json",
    "project_manifest.json",
    "memory_manifest.json",
    "run_summary.json",
    "timeline.json",
    "commands.json",
    "workspace_snapshot.json",
}

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".toml",
}


def classify_task(command: str) -> TaskType:
    text = command.lower()
    if any(term in text for term in ("homepage copy", "landing page copy", "website copy", "improve homepage copy", "hero copy")):
        return "website_copy_update"
    if any(term in text for term in ("homepage", "website", "ui", "css", "template", "page")):
        return "website_ui_update"
    if any(term in text for term in ("backend", "api endpoint", "fastapi", "route", "database")):
        return "backend_code_change"
    if any(term in text for term in ("frontend", "react", "component", "tsx", "dashboard", "panel")):
        return "frontend_code_change"
    if any(term in text for term in ("bug", "fix", "error", "traceback", "broken")):
        return "bug_fix"
    if any(term in text for term in ("readme", "docs", "documentation")):
        return "documentation_update"
    if any(term in text for term in ("data", "json", "content", "copy")):
        return "data_content_update"
    return "mixed_code_task"


def is_focused_website_update(command: str) -> bool:
    text = command.lower()
    prototype_terms = (
        "build a full prototype",
        "create a full prototype",
        "create full business",
        "complete initial project",
        "full greek yogurt prototype",
        "launch full",
        "new prototype",
        "create a simple greek yogurt order website prototype",
    )
    if any(term in text for term in prototype_terms):
        return False
    edit_terms = (
        "improve homepage copy",
        "update homepage",
        "edit hero headline",
        "hero headline",
        "subheadline",
        "update website copy",
        "only edit website/templates/index.html",
        "only update homepage/content files",
        "website copy update",
        "landing page copy",
        "homepage content",
        "homepage hero",
        "copy/content files",
    )
    return any(term in text for term in edit_terms)


def prompt_file_scope(command: str, task_type: TaskType | None = None) -> AllowedUserFileScope:
    text = command.lower()
    normalized_command = command.replace("\\", "/")
    explicit_paths = _explicit_only_paths(normalized_command)
    if explicit_paths:
        return AllowedUserFileScope(
            scope_type="exact_file",
            allowed_user_files=explicit_paths,
            blocked_user_files=[],
            reason=f"User explicitly restricted edits to: {', '.join(explicit_paths)}.",
        )
    active_task_type = task_type or classify_task(command)
    if active_task_type == "website_copy_update" or any(term in text for term in ("only update homepage/content files", "homepage copy", "copy/content files")):
        return AllowedUserFileScope(
            scope_type="homepage_content",
            allowed_user_files=["website/templates/index.html", "website/data/faqs.json", "website/README.md"],
            blocked_user_files=[
                "website/app.py",
                "website/requirements.txt",
                "website/data/sample_orders.json",
                "website/templates/status.html",
                "website/data/order_statuses.json",
            ],
            reason="User requested a homepage/content copy update only.",
        )
    return AllowedUserFileScope(
        scope_type="task_default",
        allowed_user_files=[],
        blocked_user_files=[],
        reason="No exact prompt-level user file scope was declared; task policy applies.",
    )


def allowed_by_prompt_scope(path: str, scope: AllowedUserFileScope) -> tuple[bool, str]:
    normalized = path.replace("\\", "/")
    if is_system_metadata(normalized):
        return True, "System metadata is managed separately."
    if normalized in scope.blocked_user_files:
        return False, f"Blocked by prompt-level {scope.scope_type} scope: {scope.reason}"
    if scope.allowed_user_files and normalized not in scope.allowed_user_files:
        return False, f"Outside prompt-level {scope.scope_type} scope. Allowed user files: {', '.join(scope.allowed_user_files)}."
    return True, ""


def _explicit_only_paths(command: str) -> list[str]:
    text = command.lower()
    if not any(phrase in text for phrase in ("only edit", "only update", "only change", "only modify")):
        return []
    paths = []
    for raw in command.replace(",", " ").replace(";", " ").split():
        token = raw.strip("`'\".()[]{}")
        lowered = token.lower()
        if "/" in token and lowered.startswith(("website/", "backend/", "frontend/", "docs/")):
            paths.append(token)
    return sorted({path.replace("\\", "/") for path in paths})


def is_system_metadata(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    return name in SYSTEM_METADATA_NAMES or "memory_manifest" in normalized or "context_packet" in normalized


def is_protected_path(path: str) -> tuple[bool, str]:
    normalized = Path(path.replace("\\", "/"))
    parts = {part.lower() for part in normalized.parts}
    name = normalized.name.lower()
    suffix = normalized.suffix.lower()
    if normalized.is_absolute() or ".." in normalized.parts:
        return True, "Path traversal or absolute paths are not allowed."
    if parts & PROTECTED_PARTS:
        return True, "Runtime, dependency, cache, log, or hidden workspace paths are protected."
    if name in SECRET_NAMES or name.endswith(tuple(SECRET_SUFFIXES)) or suffix in SECRET_SUFFIXES:
        return True, "Secret, credential, token, key, or environment files are protected."
    if suffix and suffix not in TEXT_EXTENSIONS:
        return True, "Non-text or unsupported extension is protected."
    return False, ""


def allowed_for_task(path: str, task_type: TaskType) -> tuple[bool, str]:
    normalized = path.replace("\\", "/")
    protected, reason = is_protected_path(normalized)
    if protected:
        return False, reason
    if is_system_metadata(normalized):
        return False, "System metadata is updated by the workspace manager, not the coding agent."
    if task_type == "website_copy_update":
        if normalized.startswith("website/data/") and not any(term in normalized for term in ("faq", "content", "copy")):
            return False, "Homepage-copy tasks must not modify order/status/sample data unless explicitly requested."
        allowed = (
            normalized.startswith("website/templates/")
            or normalized.startswith("website/data/")
            or normalized == "website/README.md"
            or normalized.startswith("docs/")
        )
        return (True, "") if allowed else (False, "Homepage-copy tasks are limited to website templates, website data, README, or docs.")
    if task_type in {"website_ui_update", "data_content_update"}:
        allowed = normalized.startswith("website/") or normalized.startswith("docs/")
        return (True, "") if allowed else (False, "Website/content tasks are limited to website/ or docs/.")
    if task_type == "backend_code_change":
        allowed = normalized.startswith("backend/app/") or normalized.startswith("backend/tests/") or normalized.startswith("tests/")
        return (True, "") if allowed else (False, "Backend tasks are limited to backend app/test files.")
    if task_type == "frontend_code_change":
        allowed = normalized.startswith("frontend/src/") or normalized.startswith("frontend/tests/")
        return (True, "") if allowed else (False, "Frontend tasks are limited to frontend source/test files.")
    return True, ""


def contains_secret_like_text(content: str) -> bool:
    lowered = content.lower()
    secret_markers = ["sk-", "api_key=", "private key", "-----begin", "password=", "token="]
    return any(marker in lowered for marker in secret_markers)
