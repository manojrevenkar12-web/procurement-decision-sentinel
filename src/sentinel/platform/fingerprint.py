"""Near-duplicate text: syndicated copies of an article skip the model call."""

from __future__ import annotations

import re


def shingles(text: str, n: int = 3) -> frozenset[str]:
    words = re.findall(r"[a-z0-9.%]+", text.lower())
    return frozenset(" ".join(words[i : i + n]) for i in range(max(1, len(words) - n + 1)))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
