from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agent.prompts import build_messages
from app.config import Settings
from app.services.retrieval import Evidence


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    citation_ids: list[int]
    grounded: bool


class AnswerDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    citation_ids: list[int] = Field(min_length=1, max_length=10)


class ExtractiveLLM:
    def generate(self, question: str, evidence: list[Evidence]) -> AnswerResult:
        if not evidence:
            return AnswerResult("未在可访问且生效的合同或合规档案中找到足够依据，请核对原始档案。", [], False)
        selected = evidence[:3]
        lines = [f"【来源 {i}】{item.excerpt[:240]}" for i, item in enumerate(selected, start=1)]
        return AnswerResult("\n".join(lines), list(range(1, len(selected) + 1)), True)


class OpenAILLM:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=30, max_retries=2)
        self.model = settings.openai_model
        self.prompt_version = settings.prompt_version
        self.fallback = ExtractiveLLM()

    def generate(self, question: str, evidence: list[Evidence]) -> AnswerResult:
        if not evidence:
            return self.fallback.generate(question, evidence)
        response = self.client.responses.parse(
            model=self.model,
            input=build_messages(question, [(i, e.title, e.excerpt, e.version) for i, e in enumerate(evidence, start=1)], self.prompt_version),
            text_format=AnswerDraft,
        )
        draft = response.output_parsed
        if draft is None or not set(draft.citation_ids).issubset(set(range(1, len(evidence) + 1))):
            return self.fallback.generate(question, evidence)
        return AnswerResult(draft.answer, sorted(set(draft.citation_ids)), True)


def make_llm(settings: Settings) -> ExtractiveLLM | OpenAILLM:
    return OpenAILLM(settings) if settings.llm_provider == "openai" else ExtractiveLLM()
