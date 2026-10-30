from __future__ import annotations

from datetime import date

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import AgentNodes
from app.agent.state import AgentState
from app.services.auth import Principal


class FinancialAgent:
    def __init__(self, nodes: AgentNodes):
        builder = StateGraph(AgentState)
        builder.add_node("retrieve", nodes.retrieve)
        builder.add_node("grade", nodes.grade)
        builder.add_node("rewrite", nodes.rewrite)
        builder.add_node("answer", nodes.answer)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "grade")
        builder.add_conditional_edges("grade", nodes.route, {"rewrite": "rewrite", "answer": "answer"})
        builder.add_edge("rewrite", "retrieve")
        builder.add_edge("answer", END)
        self.graph = builder.compile()

    def run(self, principal: Principal, question: str, as_of: date, top_k: int) -> AgentState:
        initial: AgentState = {
            "principal": principal, "question": question, "as_of": as_of, "top_k": top_k,
            "query": question, "attempts": 0, "evidence": [], "sufficient": False,
            "answer": "", "grounded": False, "citations": [],
        }
        # 异步调用
        return self.graph.invoke(initial, config={"recursion_limit": 12})
