from __future__ import annotations

from typing import Any

from app.learning_agent.services.embeddings import cosine_similarity, embed_text, tokenize
from app.learning_agent.services.source_store import get_chunks_for_docs


def search_chunks(question: str, *, doc_ids: list[str] | None = None, user_id: str = "local-user", top_k: int = 6) -> list[dict[str, Any]]:
    chunks = get_chunks_for_docs(doc_ids, user_id)
    if not chunks:
        return []
    query_embedding = embed_text(question)
    query_tokens = set(tokenize(question))
    scored = []
    for chunk in chunks:
        similarity = cosine_similarity(query_embedding, chunk.get("embedding") or [])
        chunk_tokens = set(tokenize(chunk.get("text") or ""))
        lexical = len(query_tokens & chunk_tokens) / max(len(query_tokens), 1)
        score = (0.78 * similarity) + (0.22 * lexical)
        scored.append({**chunk, "score": round(float(score), 4)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def confidence_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "low"
    best = results[0].get("score", 0)
    if best >= 0.38 or len(results) >= 4 and best >= 0.24:
        return "high"
    if best >= 0.18:
        return "medium"
    return "low"


def source_summaries(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact, de-duplicated source cards for the UI.

    Retrieval can return several chunks from the same PDF or URL. Showing every chunk
    makes the Learning Agent look noisy, so we group by document/file and keep only
    the best match plus up to two page/file references for each source.
    """
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []

    for item in results:
        meta = item.get("metadata") or {}
        source_type = meta.get("source_type")
        # PDF/URL/text sources should appear once per uploaded document. GitHub can
        # appear once per file because file path is meaningful evidence.
        key = (
            meta.get("doc_id"),
            meta.get("file_path") if source_type == "github" else None,
            meta.get("url") if not meta.get("doc_id") else None,
            meta.get("source") if not meta.get("doc_id") else None,
        )
        if key not in grouped:
            grouped[key] = {
                "doc_id": meta.get("doc_id"),
                "title": meta.get("title") or meta.get("source") or meta.get("repo") or "Source",
                "source_type": source_type,
                "source": meta.get("source") or meta.get("url") or meta.get("repo") or meta.get("file_path") or meta.get("title"),
                "page": meta.get("page"),
                "pages": [],
                "file_path": meta.get("file_path"),
                "url": meta.get("url"),
                "score": item.get("score", 0),
                "preview": (item.get("text") or "")[:220].replace("\n", " "),
                "match_count": 0,
            }
            order.append(key)

        entry = grouped[key]
        entry["match_count"] += 1
        if item.get("score", 0) > entry.get("score", 0):
            entry["score"] = item.get("score", 0)
            entry["preview"] = (item.get("text") or "")[:220].replace("\n", " ")
        page = meta.get("page")
        if page and page not in entry["pages"] and len(entry["pages"]) < 2:
            entry["pages"].append(page)
        # Keep up to two file/page-like references, not every matched chunk.
        if not entry.get("page") and page:
            entry["page"] = page

    sources = [grouped[key] for key in order]
    sources.sort(key=lambda source: source.get("score", 0), reverse=True)
    return sources[:4]
