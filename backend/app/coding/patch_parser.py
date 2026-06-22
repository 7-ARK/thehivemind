from __future__ import annotations

import json

from app.coding.schemas import ProposedPatch


def parse_proposed_patch(text: str) -> ProposedPatch:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    return ProposedPatch.model_validate(payload)
