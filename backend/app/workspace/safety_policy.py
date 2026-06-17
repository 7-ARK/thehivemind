from pathlib import Path

from fastapi import HTTPException


ALLOWED_EXTENSIONS = {
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

DENIED_PATH_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "secrets",
}

DENIED_NAMES = {".env"}
DENIED_SUFFIXES = {".env"}

ALLOWED_COMMAND_PREFIXES = (
    ("python", "--version"),
    ("python", "-m", "py_compile"),
    ("python", "-m", "pytest"),
    ("pytest",),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("npm", "test"),
)

DENIED_COMMANDS = {
    "rm",
    "del",
    "rmdir",
    "format",
    "curl",
    "wget",
    "ssh",
    "scp",
    "docker",
    "powershell",
    "pwsh",
    "cmd",
}


def validate_relative_path(relative_path: str, *, allow_directory: bool = False) -> Path:
    normalized = Path(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise HTTPException(status_code=400, detail="Path traversal and absolute paths are not allowed.")
    lower_parts = {part.lower() for part in normalized.parts}
    if lower_parts & DENIED_PATH_PARTS:
        raise HTTPException(status_code=400, detail="Path is blocked by workspace policy.")
    name = normalized.name.lower()
    if name in DENIED_NAMES or name.endswith(tuple(DENIED_SUFFIXES)):
        raise HTTPException(status_code=400, detail="Environment files are blocked by workspace policy.")
    if not allow_directory:
        suffix = normalized.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File extension '{suffix or '<none>'}' is not allowed.")
    return normalized


def resolve_inside(root: Path, relative_path: str, *, allow_directory: bool = False) -> Path:
    normalized = validate_relative_path(relative_path, allow_directory=allow_directory)
    root_resolved = root.resolve()
    target = (root_resolved / normalized).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="Resolved path escapes workspace.")
    return target


def validate_command(command: list[str]) -> tuple[bool, str | None]:
    if not command:
        return False, "Command cannot be empty."
    executable = command[0].lower()
    if executable in DENIED_COMMANDS:
        return False, f"Command '{command[0]}' is blocked by workspace policy."
    if len(command) >= 2 and (command[0].lower(), command[1].lower()) == ("git", "push"):
        return False, "git push is blocked by workspace policy."
    if len(command) >= 2 and (command[0].lower(), command[1].lower()) == ("git", "reset"):
        return False, "git reset is blocked by workspace policy."
    if command[0].lower() == "pip" and len(command) >= 2 and command[1].lower() == "install":
        return False, "pip install is blocked by workspace policy."
    if command[0].lower() == "npm" and len(command) >= 2 and command[1].lower() == "install":
        return False, "npm install is blocked by workspace policy."

    lowered = tuple(part.lower() for part in command)
    for prefix in ALLOWED_COMMAND_PREFIXES:
        if lowered[: len(prefix)] == prefix:
            return True, None
    return False, "Command is not in the safe allowlist."
