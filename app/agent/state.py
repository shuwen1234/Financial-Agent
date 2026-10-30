from __future__ import annotations

from datetime import date
from typing import TypedDict

from app.schemas.chat import Citation
from app.services.auth import Principal
from app.services.retrieval import Evidence


class AgentState(TypedDict):
    principal: Principal
    question: str
    as_of: date
    top_k: int
    query: str
    attempts: int
    evidence: list[Evidence]
    sufficient: bool
    answer: str
    grounded: bool
    citations: list[Citation]
