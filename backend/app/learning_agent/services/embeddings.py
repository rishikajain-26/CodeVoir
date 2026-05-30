from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

DIMENSIONS = 384
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,}")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "")]


def embed_text(text: str) -> list[float]:
    """Deterministic local embedding.

    This keeps the learning agent working even without paid embedding APIs. It is
    intentionally simple but useful for hackathon-scale semantic retrieval. The
    LLM provider can still be Gemini/OpenAI through CodeVoir's existing gateway.
    """
    tokens = tokenize(text)
    if not tokens:
        return [0.0] * DIMENSIONS
    counts = Counter(tokens)
    vector = [0.0] * DIMENSIONS
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSIONS
        sign = -1.0 if digest[4] % 2 else 1.0
        # log dampening prevents repeated words from dominating.
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))
