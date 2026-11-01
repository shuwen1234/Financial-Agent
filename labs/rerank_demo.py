"""对 10 个候选观察 Reranker 分数；阈值由自己的 Golden Dataset 校准。"""
from __future__ import annotations

import argparse

from app.services.retrieval import tokenize
from labs.milvus_demo import TOPICS


def run(real_model: bool, threshold: float | None) -> None:
    query = "提前还款需要什么手续？"
    candidates = [f"{topic}。" for topic in TOPICS]
    if real_model:
        from FlagEmbedding import FlagReranker

        reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=False)
        scores = reranker.compute_score([[query, text] for text in candidates])
    else:
        query_tokens = set(tokenize(query))
        scores = [float(len(query_tokens.intersection(tokenize(text)))) for text in candidates]
        print("当前为离线词面分数；加 --real-model 才是 bge-reranker 分数。")
    ranked = sorted(zip(candidates, scores), key=lambda item: item[1], reverse=True)
    for index, (text, score) in enumerate(ranked, start=1):
        print(f"{index:2d}. score={score:8.4f} {text}")
    margin = ranked[0][1] - ranked[1][1]
    print("top1-top2 margin:", round(margin, 4))
    if threshold is not None:
        print("拒答判断:", "证据不足" if ranked[0][1] < threshold else "可进入生成阶段")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-model", action="store_true")
    parser.add_argument("--threshold", type=float, help="仅用于实验；真实阈值须从标注数据校准")
    args = parser.parse_args()
    run(args.real_model, args.threshold)
