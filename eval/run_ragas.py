"""独立 RAGAS 环境运行四指标；只评估有标注答案的正样本。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ragas import EvaluationDataset, evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

source = Path(__file__).resolve().parent / "results" / "top_3.json"
if not source.exists():
    raise SystemExit("先在主项目环境运行 python -m eval.run_offline --top-k 3")
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("RAGAS 独立环境需要有效的 OPENAI_API_KEY；不要把真实合同数据发往未获授权的服务")
raw = json.loads(source.read_text(encoding="utf-8"))
rows = [
    {"user_input": item["question"], "retrieved_contexts": item["retrieved_contexts"],
     "response": item["response"], "reference": item["reference"]}
    for item in raw if not item["should_refuse"]
]
dataset = EvaluationDataset.from_list(rows)
result = evaluate(dataset=dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
print(result)
