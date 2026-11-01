"""不调用外部模型的 10 条回归：引用命中、拒答、答案关键事实。"""
from __future__ import annotations

import argparse
import json
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

ROOT = Path(__file__).resolve().parent


def run(top_k: int) -> list[dict]:
    golden = json.loads((ROOT / "golden.json").read_text(encoding="utf-8"))
    fixtures = json.loads((ROOT / "fixtures.json").read_text(encoding="utf-8"))
    principal = Principal("eval-user", "eval-tenant", frozenset({"archive_reader", "archive_writer", "legal"}), Classification.restricted)
    with tempfile.TemporaryDirectory() as folder:
        store = ArchiveStore(Path(folder) / "eval.db", max_candidates=100)
        for raw in fixtures:
            store.ingest(principal, ArchiveCreate.model_validate(raw), "eval-ingest")
        agent = FinancialAgent(AgentNodes(RetrievalService(store), ExtractiveLLM()))
        rows: list[dict] = []
        for item in golden:
            state = agent.run(principal, item["question"], date(2026, 10, 30), top_k)
            citations = state["citations"]
            rows.append({
                **item,
                "response": state["answer"],
                "retrieved_contexts": [citation.excerpt for citation in citations],
                "cited_doc_ids": [citation.doc_id for citation in citations],
                "citation_scores": [citation.score for citation in citations],
                "grounded": state["grounded"],
                "citation_hit": item["expected_doc_id"] in [c.doc_id for c in citations] if not item["should_refuse"] else None,
                "refusal_correct": not state["grounded"] if item["should_refuse"] else None,
                "answer_contains": item["reference"] in state["answer"] if not item["should_refuse"] else None,
            })
        return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=3, choices=range(1, 11))
    args = parser.parse_args()
    rows = run(args.top_k)
    positives = [row for row in rows if not row["should_refuse"]]
    negatives = [row for row in rows if row["should_refuse"]]
    print(f"top_k={args.top_k}  引用命中={sum(x['citation_hit'] for x in positives)}/{len(positives)}  "
          f"答案关键事实={sum(x['answer_contains'] for x in positives)}/{len(positives)}  "
          f"拒答正确={sum(x['refusal_correct'] for x in negatives)}/{len(negatives)}")
    output = ROOT / "results" / f"top_{args.top_k}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("详细结果:", output)


if __name__ == "__main__":
    main()
