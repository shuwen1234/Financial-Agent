"""Checkpointer、interrupt、Send 与 recursion_limit 的最小实验。"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt


class ReviewState(TypedDict):
    text: str
    approved: bool


def review(state: ReviewState) -> dict:
    decision = interrupt({"question": "是否发布这段示例内容？", "preview": state["text"]})
    return {"approved": bool(decision["approved"])}


def interrupt_demo() -> None:
    builder = StateGraph(ReviewState)
    builder.add_node("review", review)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "review-lab-1"}}
    pending = graph.invoke({"text": "虚构的合规条款", "approved": False}, config=config)
    print("暂停:", pending)
    resumed = graph.invoke(Command(resume={"approved": True}), config=config)
    print("人工审核后:", resumed)


class FanoutState(TypedDict):
    questions: list[str]
    answers: Annotated[list[str], operator.add]


def fanout_demo() -> None:
    builder = StateGraph(FanoutState)
    builder.add_node("plan", lambda state: {})
    builder.add_node("lookup", lambda state: {"answers": [f"已检索：{state['question']}"]})
    builder.add_node("combine", lambda state: {})
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", lambda state: [Send("lookup", {"question": q}) for q in state["questions"]])
    builder.add_edge("lookup", "combine")
    builder.add_edge("combine", END)
    graph = builder.compile()
    result = graph.invoke({"questions": ["提前还款", "违约责任"], "answers": []})
    print("并行子任务:", result["answers"])


class LoopState(TypedDict):
    count: int


def recursion_demo() -> None:
    builder = StateGraph(LoopState)
    builder.add_node("tick", lambda state: {"count": state["count"] + 1})
    builder.add_edge(START, "tick")
    builder.add_edge("tick", "tick")
    graph = builder.compile()
    try:
        graph.invoke({"count": 0}, config={"recursion_limit": 4})
    except GraphRecursionError as exc:
        print("触发 recursion_limit:", type(exc).__name__)


if __name__ == "__main__":
    interrupt_demo()
    fanout_demo()
    recursion_demo()
