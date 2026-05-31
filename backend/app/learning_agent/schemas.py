from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal["text", "url", "github", "pdf"]
GenerationType = Literal[
    "summary",
    "notes",
    "cheatsheet",
    "flashcards",
    "interview_questions",
    "revision_plan",
    "project_pitch",
    "flowchart",
    "mindmap",
    "weak_answer_rewrite",
    "source_mock_interview",
    "skill_gap_heatmap",
    "first_impression_simulator",
    "opportunity_kit",
    "judge_demo_kit",
    "architecture_map",
    "interview_replay_timeline",
    "evidence_coverage_meter",
    "knowledge_graph",
    "answer_studio",
]


class TextSourceRequest(BaseModel):
    title: str = Field(default="Text notes", max_length=180)
    content: str = Field(min_length=1)
    user_id: str = "local-user"


class UrlSourceRequest(BaseModel):
    url: str
    title: str = ""
    user_id: str = "local-user"


class GithubSourceRequest(BaseModel):
    repo_url: str
    title: str = ""
    user_id: str = "local-user"
    max_files: int = Field(default=28, ge=1, le=80)


class SourceResponse(BaseModel):
    doc_id: str
    title: str
    source_type: SourceType
    chunk_count: int
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    doc_ids: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    mode: Literal["beginner", "intermediate", "advanced", "interview", "production", "hinglish"] = "beginner"
    strict_sources: bool = True


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    confidence: str = "medium"
    suggested_followups: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    generation_type: GenerationType
    doc_ids: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    weak_topics: list[str] = Field(default_factory=list)
    extra_context: str = ""


class GenerateResponse(BaseModel):
    generation_type: str
    output: str
    sources: list[dict[str, Any]] = Field(default_factory=list)


class SessionLearningRequest(BaseModel):
    user_id: str = "local-user"
    doc_ids: list[str] = Field(default_factory=list)


class OpportunityPrepRequest(BaseModel):
    title: str
    description: str = ""
    url: str = ""
    resume_profile: dict[str, Any] = Field(default_factory=dict)
    user_id: str = "local-user"


class WeakAnswerRewriteRequest(BaseModel):
    question: str = Field(default="", max_length=1200)
    answer: str = Field(min_length=1, max_length=5000)
    target_role: str = Field(default="", max_length=160)
    user_id: str = "local-user"
    doc_ids: list[str] = Field(default_factory=list)


class MockInterviewRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    count: int = Field(default=6, ge=3, le=12)
