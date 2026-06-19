from __future__ import annotations

import re


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bkey_[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


def redact_secrets(text: str) -> tuple[str, bool]:
    redacted = text or ""
    changed = False
    for pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn("[REDACTED_SECRET]", redacted)
        changed = changed or count > 0
    return redacted, changed


def token_estimate(text: str) -> int:
    return max(1, len((text or "").split()))


def active_constraints_from_command(command: str, run_type: str) -> list[str]:
    lowered = command.lower()
    constraints = [
        "Do not use GPT-5.5 unless explicitly approved.",
        "Do not deploy, install packages, take payments, send emails, or post publicly without explicit approval.",
    ]
    if run_type == "research_only" or "research only" in lowered or "only research" in lowered:
        constraints.append("Do not update files for research_only.")
    if run_type == "website_update" or "only update website" in lowered:
        constraints.append("Only update website/ for website_update.")
    if "do not use gpt-5.5" in lowered or "no gpt-5.5" in lowered:
        constraints.append("The current command explicitly blocks GPT-5.5.")
    if "do not update files" in lowered or "no file writes" in lowered:
        constraints.append("The current command explicitly blocks file writes.")
    if "do not search" in lowered or "no web search" in lowered:
        constraints.append("The current command explicitly blocks web search.")
    return constraints
