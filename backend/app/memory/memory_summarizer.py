from __future__ import annotations

import json
import re
from typing import Any


def compact_text(text: str, limit: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned[:limit].rstrip()


def summarize_json(value: Any, limit: int = 900) -> str:
    try:
        text = json.dumps(value, ensure_ascii=True)
    except TypeError:
        text = str(value)
    return compact_text(text, limit)


def extract_warnings(text: str) -> list[str]:
    warnings = []
    for line in (text or "").splitlines():
        lowered = line.lower()
        if any(term in lowered for term in ("warning", "risk", "failed", "do not", "needs review", "human approval", "not approved")):
            warnings.append(line.strip("- ").strip())
    return [item for item in warnings if item][:8]


def source_summary(sources_payload: dict[str, Any]) -> tuple[str, list[str]]:
    sources = sources_payload.get("sources") if isinstance(sources_payload, dict) else []
    urls = [str(source.get("url")) for source in sources if isinstance(source, dict) and source.get("url")]
    titles = [str(source.get("title")) for source in sources if isinstance(source, dict) and source.get("title")]
    provider = sources_payload.get("provider_id") or "unknown"
    status = "mock fixture" if sources_payload.get("mock_fixture") else "live/current" if sources_payload.get("search_used") else "skipped"
    summary = f"{provider} search source summary: {len(urls)} source(s), status {status}. " + ", ".join(titles[:5])
    return compact_text(summary, 700), urls[:10]
