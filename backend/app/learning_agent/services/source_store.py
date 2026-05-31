from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.learning_agent.services.chunker import chunk_text, clean_text
from app.learning_agent.services.embeddings import embed_text

BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "learning_agent"
DOCS_DIR = BASE_DIR / "documents"
CHUNKS_DIR = BASE_DIR / "chunks"
OUTPUTS_DIR = BASE_DIR / "outputs"

for directory in (DOCS_DIR, CHUNKS_DIR, OUTPUTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_read(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return fallback


def create_document(
    *,
    title: str,
    source_type: str,
    raw_items: list[dict[str, Any]],
    user_id: str = "local-user",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    final_title = title.strip() or _default_title(source_type, metadata or {})
    chunks: list[dict[str, Any]] = []
    total_chars = 0

    for item_index, item in enumerate(raw_items):
        text = clean_text(str(item.get("text") or ""))
        if not text:
            continue
        total_chars += len(text)
        item_meta = {k: v for k, v in item.items() if k != "text" and v is not None}
        for chunk_index, chunk in enumerate(chunk_text(text)):
            chunk_id = f"{doc_id}_{len(chunks)}"
            merged_meta = {
                "doc_id": doc_id,
                "title": final_title,
                "source_type": source_type,
                "item_index": item_index,
                "chunk_index": chunk_index,
                **(metadata or {}),
                **item_meta,
            }
            chunks.append({
                "id": chunk_id,
                "doc_id": doc_id,
                "text": chunk,
                "metadata": merged_meta,
                "embedding": embed_text(chunk),
            })

    document = {
        "doc_id": doc_id,
        "title": final_title,
        "source_type": source_type,
        "user_id": user_id or "local-user",
        "created_at": _now(),
        "updated_at": _now(),
        "chunk_count": len(chunks),
        "total_chars": total_chars,
        "metadata": metadata or {},
    }
    (DOCS_DIR / f"{doc_id}.json").write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding="utf-8")
    (CHUNKS_DIR / f"{doc_id}.json").write_text(json.dumps(chunks, ensure_ascii=True), encoding="utf-8")
    return document


def _default_title(source_type: str, metadata: dict[str, Any]) -> str:
    return metadata.get("source") or metadata.get("url") or metadata.get("repo") or f"{source_type.title()} source"


def list_documents(user_id: str = "local-user") -> list[dict[str, Any]]:
    docs = []
    for path in sorted(DOCS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        doc = _safe_json_read(path, None)
        if not doc:
            continue
        if user_id and user_id != "all" and doc.get("user_id", "local-user") not in {user_id, "local-user"}:
            continue
        docs.append(doc)
    return docs


def get_document(doc_id: str) -> dict[str, Any] | None:
    return _safe_json_read(DOCS_DIR / f"{doc_id}.json", None)


def get_chunks(doc_id: str) -> list[dict[str, Any]]:
    return _safe_json_read(CHUNKS_DIR / f"{doc_id}.json", [])


def get_chunks_for_docs(doc_ids: list[str] | None, user_id: str = "local-user") -> list[dict[str, Any]]:
    visible_ids = {doc["doc_id"] for doc in list_documents(user_id)}
    ids = [doc_id for doc_id in (doc_ids or list(visible_ids)) if doc_id in visible_ids]
    chunks: list[dict[str, Any]] = []
    for doc_id in ids:
        chunks.extend(get_chunks(doc_id))
    return chunks


def delete_document(doc_id: str, user_id: str = "local-user") -> bool:
    document = get_document(doc_id)
    if not document:
        return False
    if user_id and user_id != "all" and document.get("user_id", "local-user") not in {user_id, "local-user"}:
        return False
    for path in (DOCS_DIR / f"{doc_id}.json", CHUNKS_DIR / f"{doc_id}.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
    return True


def save_generated_output(user_id: str, generation_type: str, content: str, doc_ids: list[str], sources: list[dict[str, Any]]) -> dict[str, Any]:
    output_id = f"out_{uuid.uuid4().hex[:12]}"
    output = {
        "output_id": output_id,
        "user_id": user_id or "local-user",
        "generation_type": generation_type,
        "doc_ids": doc_ids,
        "content": content,
        "sources": sources,
        "created_at": _now(),
    }
    (OUTPUTS_DIR / f"{output_id}.json").write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")
    return output
