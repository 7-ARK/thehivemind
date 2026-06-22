from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.coding.schemas import ProposedPatch


class PatchParseError(ValueError):
    def __init__(self, message: str, *, parser_route: str = "unknown") -> None:
        super().__init__(message)
        self.parser_route = parser_route


@dataclass(frozen=True)
class ParsedPatch:
    patch: ProposedPatch
    parser_route: str


PARSER_ROUTES = ["pure_json", "fenced_json", "embedded_json", "tool_arguments"]


def parse_proposed_patch(text: str) -> ProposedPatch:
    return parse_proposed_patch_with_route(text).patch


def parse_proposed_patch_with_route(text: str, *, tool_arguments: list[str] | None = None) -> ParsedPatch:
    if not (text or "").strip() and not any((item or "").strip() for item in tool_arguments or []):
        raise PatchParseError("Coding provider returned empty completion; no patch was applied.", parser_route="empty")

    candidates: list[tuple[str, str]] = []
    stripped = (text or "").strip()
    if stripped:
        candidates.append(("pure_json", stripped))
        fenced = _strip_markdown_fence(stripped)
        if fenced != stripped:
            candidates.append(("fenced_json", fenced))
        candidates.extend(("embedded_json", item) for item in _embedded_json_candidates(stripped))
    for arguments in tool_arguments or []:
        if (arguments or "").strip():
            candidates.append(("tool_arguments", arguments.strip()))

    errors: list[str] = []
    saw_valid_json = False
    for route, candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(f"{route}: {exc.msg}")
            continue
        saw_valid_json = True
        try:
            return ParsedPatch(patch=_normalize_patch_payload(payload), parser_route=route)
        except PatchParseError:
            raise
        except ValidationError as exc:
            errors.append(f"{route}: {exc.errors()[0].get('msg', str(exc))}")
        except Exception as exc:
            errors.append(f"{route}: {exc}")

    if saw_valid_json:
        raise PatchParseError("Coding provider response did not include a valid files patch; no patch was applied.", parser_route="schema_validation")
    detail = "; ".join(errors[:4]) or "no JSON object found"
    raise PatchParseError(f"Coding provider returned malformed JSON; no patch was applied. {detail}", parser_route="malformed_json")


def _normalize_patch_payload(payload: Any) -> ProposedPatch:
    if not isinstance(payload, dict):
        raise PatchParseError("Coding provider JSON root must be an object; no patch was applied.", parser_route="schema_validation")
    if "files_to_change" in payload:
        return ProposedPatch.model_validate(payload)
    if "files" not in payload:
        raise PatchParseError("Coding provider response did not include required files field; no patch was applied.", parser_route="missing_files")
    files = payload.get("files")
    if not isinstance(files, list):
        raise PatchParseError("Coding provider files field must be a list; no patch was applied.", parser_route="missing_files")

    files_to_change = []
    for index, item in enumerate(files, start=1):
        if not isinstance(item, dict):
            raise PatchParseError(f"Coding provider files[{index}] must be an object; no patch was applied.", parser_route="schema_validation")
        if not item.get("path"):
            raise PatchParseError(f"Coding provider files[{index}] is missing path; no patch was applied.", parser_route="schema_validation")
        if "content" not in item and "new_content" not in item and "edits" not in item:
            raise PatchParseError(f"Coding provider files[{index}] is missing complete file content or edits; no patch was applied.", parser_route="schema_validation")
        files_to_change.append(
            {
                "path": item["path"],
                "reason": item.get("reason") or "Provider proposed complete-file update.",
                "change_type": item.get("change_type") or "modify",
                "new_content": item.get("content") if "content" in item else item.get("new_content"),
                "edits": item.get("edits") or [],
            }
        )

    normalized = {
        "summary": payload.get("summary") or "Structured coding patch from provider.",
        "task_type": payload.get("task_type") or "mixed_code_task",
        "files_to_change": files_to_change,
        "files_read": payload.get("files_read") or [],
        "validation_commands": payload.get("validation_commands") or [],
        "risk_notes": payload.get("risk_notes") or [],
        "memory_used": payload.get("memory_used") or [],
    }
    return ProposedPatch.model_validate(normalized)


def _strip_markdown_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if len(lines) < 2 or not lines[0].strip().startswith("```") or not lines[-1].strip().startswith("```"):
        return text
    return "\n".join(lines[1:-1]).strip()


def _embedded_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            _payload, end = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        candidate = text[start : start + end].strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates
