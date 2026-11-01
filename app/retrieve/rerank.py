"""可选 BGE 重排；拒答阈值须在自己的 Golden Dataset 上校准。"""
from __future__ import annotations

from dataclasses import replace

from app.config import Settings
from app.services.retrieval import Evidence


class BGEReranker:
    def __init__(self, threshold: float | None):
        try:
            from FlagEmbedding import FlagReranker
        except ImportError as exc:
            raise RuntimeError("BGE 重排模式需要安装 FlagEmbedding") from exc
        self.model = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=False)
        self.threshold = threshold

    def rerank(self, query: str, candidates: list[Evidence], top_k: int) -> list[Evidence]:
        if not candidates:
            return []
        scores = self.model.compute_score([[query, item.excerpt] for item in candidates])
        if isinstance(scores, (float, int)):
            scores = [scores]
        reranked = sorted(
            (replace(item, score=round(float(score), 4)) for item, score in zip(candidates, scores)),
            key=lambda item: item.score, reverse=True,
        )
        if self.threshold is not None and reranked[0].score < self.threshold:
            return []
        return reranked[:top_k]


def make_reranker(settings: Settings) -> BGEReranker | None:
    return BGEReranker(settings.rerank_min_score) if settings.reranker_mode == "bge" else None
