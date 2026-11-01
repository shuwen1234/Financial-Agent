from __future__ import annotations

from app.agent.state import AgentState
from app.retrieve.glossary import normalize_query
from app.schemas.chat import Citation
from app.services.llm import ExtractiveLLM, OpenAILLM
from app.services.retrieval import RetrievalService

MAX_ATTEMPTS = 2


class AgentNodes:
    def __init__(self, retrieval: RetrievalService, llm: ExtractiveLLM | OpenAILLM):
        self.retrieval = retrieval
        self.llm = llm

    def plan(self, state: AgentState) -> dict:
        return {
            "query": normalize_query(state["question"]),
            "plan": ["归一检索词", "检索可访问且生效的档案", "核对证据并生成引用"],
        }

    def retrieve(self, state: AgentState) -> dict:
        evidence = self.retrieval.search(state["principal"], state["query"], state["as_of"], state["top_k"])
        return {"evidence": evidence, "attempts": state["attempts"] + 1}

    def grade(self, state: AgentState) -> dict:
        return {"sufficient": bool(state["evidence"])}

    def route(self, state: AgentState) -> str:
        return "synthesize" if state["sufficient"] or state["attempts"] >= MAX_ATTEMPTS else "rewrite"

    def rewrite(self, state: AgentState) -> dict:
        replacements = {"违约金": "违约责任", "合同到期": "合同终止", "监管规定": "合规要求"}
        query = state["query"]
        for old, new in replacements.items():
            query = query.replace(old, new)
        return {"query": query}

    def synthesize(self, state: AgentState) -> dict:
        result = self.llm.generate(state["question"], state["evidence"])
        citations = [
            Citation(source_id=i, doc_id=state["evidence"][i - 1].doc_id,
                     version=state["evidence"][i - 1].version,
                     title=state["evidence"][i - 1].title,
                     excerpt=state["evidence"][i - 1].excerpt,
                     score=state["evidence"][i - 1].score,
                     parent_id=state["evidence"][i - 1].parent_id,
                     section_path=state["evidence"][i - 1].section_path)
            for i in result.citation_ids
        ]
        return {"answer": result.answer, "grounded": result.grounded, "citations": citations}
