"""v1/v2 Prompt 对照；只有显式 --live 才调用已配置模型。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.prompts.loader import PromptRegistry
from app.services.llm import OpenAILLM
from app.services.retrieval import Evidence

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="对虚构 Golden 样本调用真实模型")
    parser.add_argument("--max-cases", type=int, default=2)
    args = parser.parse_args()
    registry = PromptRegistry()
    for version in ("v1", "v2"):
        spec = registry.load("answer", version)
        print(version, "variables:", spec.variables, "system_chars:", len(spec.system))
    if not args.live:
        print("仅校验 Prompt 文件；加 --live 才做模型回归。")
        return
    settings = Settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise SystemExit("--live 需要配置 OPENAI_API_KEY 与 OPENAI_MODEL")
    source = ROOT / "results" / "top_3.json"
    if not source.exists():
        raise SystemExit("先运行 python -m eval.run_offline --top-k 3")
    rows = [item for item in json.loads(source.read_text(encoding="utf-8")) if not item["should_refuse"]][:args.max_cases]
    results = []
    for version in ("v1", "v2"):
        llm = OpenAILLM(settings.model_copy(update={"prompt_version": version}))
        for item in rows:
            evidence = [Evidence(doc_id, 1, doc_id, excerpt, 0.0) for doc_id, excerpt in zip(item["cited_doc_ids"], item["retrieved_contexts"])]
            answer = llm.generate(item["question"], evidence)
            results.append({"version": version, "question": item["question"], "answer": answer.answer,
                            "citation_ids": answer.citation_ids, "reference_contains": item["reference"] in answer.answer})
    output = ROOT / "results" / "prompt_compare.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for version in ("v1", "v2"):
        subset = [row for row in results if row["version"] == version]
        print(version, "关键事实包含:", sum(row["reference_contains"] for row in subset), "/", len(subset))
    print("详细结果:", output)


if __name__ == "__main__":
    main()
