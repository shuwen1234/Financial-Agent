"""用虚构档案向 Langfuse 发送一条 LangGraph Trace。"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

from app.agent.graph import FinancialAgent
from app.agent.nodes import AgentNodes
from app.schemas.archive import ArchiveCreate, Classification
from app.services.archive import ArchiveStore
from app.services.auth import Principal
from app.services.llm import ExtractiveLLM
from app.services.retrieval import RetrievalService


def main() -> None:
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        raise SystemExit("先在运行环境设置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY；仅使用虚构档案")
    from langfuse import get_client
    from langfuse.langchain import CallbackHandler

    with tempfile.TemporaryDirectory() as folder:
        principal = Principal("lab-user", "lab-tenant", frozenset({"legal"}), Classification.internal)
        store = ArchiveStore(Path(folder) / "lab.db", 20)
        store.ingest(principal, ArchiveCreate(
            doc_id="LAB-CONTRACT", version=1, title="虚构合同", classification=Classification.internal,
            acl_roles=["legal"], effective_from=date(2026, 1, 1),
            content="第七条 提前还款需提前三十日提交申请。",
        ), "lab-ingest")
        agent = FinancialAgent(AgentNodes(RetrievalService(store), ExtractiveLLM()))
        handler = CallbackHandler()
        result = agent.graph.invoke(
            agent.initial_state(principal, "提前还款提前多少天？", date(2026, 10, 30), 3),
            config={"callbacks": [handler], "recursion_limit": 12},
        )
        get_client().flush()
        print("已发送虚构样本 Trace；回答:", result["answer"])


if __name__ == "__main__":
    main()
