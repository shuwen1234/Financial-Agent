from __future__ import annotations

from datetime import date

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import AgentNodes
from app.agent.state import AgentState
from app.services.auth import Principal


class FinancialAgent:
    def __init__(self, nodes: AgentNodes):
        builder = StateGraph(AgentState)
        builder.add_node("plan", nodes.plan)
        builder.add_node("retrieve", nodes.retrieve)
        builder.add_node("grade", nodes.grade)
        builder.add_node("rewrite", nodes.rewrite)
        builder.add_node("synthesize", nodes.synthesize)
        builder.add_edge(START, "plan")
        builder.add_edge("plan", "retrieve")
        builder.add_edge("retrieve", "grade")
        builder.add_conditional_edges("grade", nodes.route, {"rewrite": "rewrite", "synthesize": "synthesize"})
        builder.add_edge("rewrite", "retrieve")
        builder.add_edge("synthesize", END)
        self.graph = builder.compile()

    @staticmethod
    def initial_state(principal: Principal, question: str, as_of: date, top_k: int) -> AgentState:
        return {
            "principal": principal, "question": question, "plan": [], "as_of": as_of, "top_k": top_k,
            "query": question, "attempts": 0, "evidence": [], "sufficient": False,
            "answer": "", "grounded": False, "citations": [],
        }

    def run(self, principal: Principal, question: str, as_of: date, top_k: int) -> AgentState:
        return self.graph.invoke(self.initial_state(principal, question, as_of, top_k), config={"recursion_limit": 12})

    async def stream_updates(self, principal: Principal, question: str, as_of: date, top_k: int):
        async for event in self.graph.astream(
            self.initial_state(principal, question, as_of, top_k),
            config={"recursion_limit": 12}, stream_mode="updates",
        ):
            yield event
