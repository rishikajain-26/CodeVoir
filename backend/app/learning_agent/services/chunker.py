from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    overlap = max(0, min(overlap, chunk_size - 1))
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            # Prefer splitting near a paragraph/sentence boundary.
            boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + int(chunk_size * 0.55):
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks
