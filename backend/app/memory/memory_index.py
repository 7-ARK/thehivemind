from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "only",
    "were",
    "was",
    "are",
    "not",
    "but",
    "run",
}


def normalize_text(text: str) -> str:
    return " ".join(tokenize(text))


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_\-]+", (text or "").lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def sparse_vector(text: str) -> dict[str, float]:
    counts = Counter(tokenize(text))
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: round(value / norm, 6) for key, value in counts.items()}


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    return sum(left[key] * right[key] for key in common)


def keywords(text: str, limit: int = 12) -> list[str]:
    return [term for term, _ in Counter(tokenize(text)).most_common(limit)]


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
