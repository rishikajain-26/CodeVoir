from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from app.learning_agent.loaders.github_loader import load_github_repo
from app.learning_agent.loaders.pdf_loader import load_pdf
from app.learning_agent.loaders.url_loader import load_url
from app.learning_agent.schemas import (
    ChatRequest,
    ChatResponse,
    GenerateRequest,
    GenerateResponse,
    GithubSourceRequest,
    OpportunityPrepRequest,
    SessionLearningRequest,
    SourceResponse,
    TextSourceRequest,
    UrlSourceRequest,
    WeakAnswerRewriteRequest,
    MockInterviewRequest,
)
from app.learning_agent.services.generator import (
    generate_material,
    generate_opportunity_prep,
    generate_session_plan,
    generate_source_mock_interview,
    generate_weak_answer_rewrite,
)
from app.learning_agent.services.rag_engine import answer_question
from app.learning_agent.services.source_store import create_document, delete_document, get_document, list_documents
from app.services.session_store import load_all_sessions

router = APIRouter(prefix="/api/learning", tags=["learning-agent"])


@router.get("/health")
def learning_health() -> dict[str, Any]:
    return {"status": "ok", "service": "codevoir-learning-agent"}


@router.get("/sources")
def sources(user_id: str = "local-user") -> list[dict[str, Any]]:
    return list_documents(user_id)


@router.delete("/sources/{doc_id}")
def delete_source(doc_id: str, user_id: str = "local-user") -> dict[str, Any]:
    if not delete_document(doc_id, user_id):
        raise HTTPException(status_code=404, detail="Source was not found.")
    return {"doc_id": doc_id, "deleted": True}


@router.post("/sources/text", response_model=SourceResponse)
def add_text_source(payload: TextSourceRequest) -> dict[str, Any]:
    doc = create_document(
        title=payload.title,
        source_type="text",
        raw_items=[{"text": payload.content, "source": payload.title}],
        user_id=payload.user_id,
        metadata={"source": payload.title},
    )
    return _source_response(doc, "Text notes indexed successfully.")


@router.post("/sources/url", response_model=SourceResponse)
def add_url_source(payload: UrlSourceRequest) -> dict[str, Any]:
    try:
        items, metadata = load_url(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = create_document(
        title=payload.title or metadata.get("title") or payload.url,
        source_type="url",
        raw_items=items,
        user_id=payload.user_id,
        metadata={"url": payload.url, "source": metadata.get("title") or payload.url, **metadata},
    )
    return _source_response(doc, "URL content fetched and indexed successfully.")


@router.post("/sources/github", response_model=SourceResponse)
def add_github_source(payload: GithubSourceRequest) -> dict[str, Any]:
    try:
        items, metadata = load_github_repo(payload.repo_url, max_files=payload.max_files)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = create_document(
        title=payload.title or metadata.get("repo") or payload.repo_url,
        source_type="github",
        raw_items=items,
        user_id=payload.user_id,
        metadata={"repo": metadata.get("repo"), "source": payload.repo_url, **metadata},
    )
    return _source_response(doc, "GitHub repository indexed successfully.")


@router.post("/sources/pdf", response_model=SourceResponse)
async def add_pdf_source(
    file: UploadFile = File(...),
    user_id: str = Form("local-user"),
    title: str = Form(""),
) -> dict[str, Any]:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported by this endpoint.")
    tmp_dir = Path(tempfile.mkdtemp(prefix="codevoir_pdf_"))
    tmp_path = tmp_dir / file.filename
    try:
        with tmp_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        items = load_pdf(tmp_path)
        if not items:
            raise ValueError("No readable text was found in this PDF.")
        doc = create_document(
            title=title or file.filename,
            source_type="pdf",
            raw_items=items,
            user_id=user_id,
            metadata={"source": file.filename, "filename": file.filename},
        )
        return _source_response(doc, "PDF uploaded and indexed successfully.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> dict[str, Any]:
    return answer_question(
        payload.question,
        doc_ids=payload.doc_ids,
        user_id=payload.user_id,
        mode=payload.mode,
        strict_sources=payload.strict_sources,
    )


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest) -> dict[str, Any]:
    result = generate_material(
        generation_type=payload.generation_type,
        doc_ids=payload.doc_ids,
        user_id=payload.user_id,
        weak_topics=payload.weak_topics,
        extra_context=payload.extra_context,
    )
    return {"generation_type": payload.generation_type, "output": result["output"], "sources": result.get("sources", [])}


@router.post("/from-session/{session_id}", response_model=GenerateResponse)
def from_session(session_id: str, payload: SessionLearningRequest) -> dict[str, Any]:
    sessions = load_all_sessions()
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session was not found.")
    result = generate_session_plan(session=session, doc_ids=payload.doc_ids, user_id=payload.user_id)
    return {"generation_type": "revision_plan", "output": result["output"], "sources": result.get("sources", [])}


@router.post("/mock-interview", response_model=GenerateResponse)
def mock_interview(payload: MockInterviewRequest) -> dict[str, Any]:
    result = generate_source_mock_interview(
        doc_ids=payload.doc_ids,
        user_id=payload.user_id,
        difficulty=payload.difficulty,
        count=payload.count,
    )
    return {"generation_type": "source_mock_interview", "output": result["output"], "sources": result.get("sources", [])}


@router.post("/weak-answer", response_model=GenerateResponse)
def weak_answer(payload: WeakAnswerRewriteRequest) -> dict[str, Any]:
    result = generate_weak_answer_rewrite(
        question=payload.question,
        answer=payload.answer,
        target_role=payload.target_role,
        doc_ids=payload.doc_ids,
        user_id=payload.user_id,
    )
    return {"generation_type": "weak_answer_rewrite", "output": result["output"], "sources": result.get("sources", [])}


@router.post("/prepare-opportunity")
def prepare_opportunity(payload: OpportunityPrepRequest) -> dict[str, Any]:
    output = generate_opportunity_prep(
        title=payload.title,
        description=payload.description,
        url=payload.url,
        resume_profile=payload.resume_profile,
        user_id=payload.user_id,
    )
    return {"output": output}


@router.get("/export/markdown/{doc_id}", response_class=PlainTextResponse)
def export_doc_summary(doc_id: str) -> str:
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return f"# {doc.get('title', 'CodeVoir source')}\n\n- Type: {doc.get('source_type')}\n- Chunks: {doc.get('chunk_count')}\n- Created: {doc.get('created_at')}\n"


def _source_response(doc: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "doc_id": doc["doc_id"],
        "title": doc["title"],
        "source_type": doc["source_type"],
        "chunk_count": doc["chunk_count"],
        "message": message,
        "metadata": doc.get("metadata") or {},
    }
