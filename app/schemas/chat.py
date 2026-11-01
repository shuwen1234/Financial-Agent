from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    as_of: date | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class Citation(BaseModel):
    source_id: int
    doc_id: str
    version: int
    title: str
    excerpt: str
    score: float
    parent_id: str = ""
    section_path: str = "正文"


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    grounded: bool
    citations: list[Citation]
    retrieval_attempts: int
    as_of: date
    plan: list[str] = Field(default_factory=list)
