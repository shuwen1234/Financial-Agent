from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from app.parse.chunker import ChildChunk, build_chunks
from app.retrieve.glossary import normalize_query
from app.services.archive import ArchiveStore, CandidateLimitExceeded
from app.services.auth import Principal

if TYPE_CHECKING:
    from app.retrieve.rerank import BGEReranker


@dataclass(frozen=True)
class Evidence:
    doc_id: str
    version: int
    title: str
    excerpt: str
    score: float
    parent_id: str = ""
    section_path: str = "正文"


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", text.lower()):
        word = match.group()
        if "\u4e00" <= word[0] <= "\u9fff":
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


class RetrievalService:
    def __init__(self, store: ArchiveStore, reranker: BGEReranker | None = None, min_token_overlap: int = 2):
        self.store = store
        self.reranker = reranker
        self.min_token_overlap = min_token_overlap

    def search(self, principal: Principal, question: str, as_of: date, top_k: int) -> list[Evidence]:
        records = [r for r in self.store.list_effective(principal.tenant_id, as_of) if principal.can_read(r.classification, r.acl_roles)]
        candidates: list[tuple[object, ChildChunk]] = []
        for record in records:
            for child in build_chunks(record.content):
                if tokenize(child.text):
                    candidates.append((record, child))
                    if len(candidates) > self.store.max_candidates * 5:
                        raise CandidateLimitExceeded("候选片段超过本地检索上限，请切换索引服务")
        if not candidates:
            return []
        token_lists = [tokenize(child.text) for _, child in candidates]
        query_tokens = tokenize(normalize_query(question))
        if not query_tokens:
            return []
        bm25_scores = BM25Okapi(token_lists).get_scores(query_tokens)
        query_set = set(query_tokens)
        best_by_parent: dict[tuple[str, int, str], Evidence] = {}
        for (record, child), doc_tokens, bm25_score in zip(candidates, token_lists, bm25_scores):
            overlap = len(query_set.intersection(doc_tokens))
            if overlap < min(self.min_token_overlap, len(query_set)):
                continue
            score = float(bm25_score) + overlap
            evidence = Evidence(record.doc_id, record.version, record.title, child.parent_text[:600],
                                round(score, 4), child.parent_id, child.section_path)
            key = (record.doc_id, record.version, child.parent_id)
            if key not in best_by_parent or evidence.score > best_by_parent[key].score:
                best_by_parent[key] = evidence
        ranked = list(best_by_parent.values())
        ranked.sort(key=lambda x: (-x.score, x.doc_id, -x.version))
        if self.reranker:
            return self.reranker.rerank(question, ranked[:max(top_k, 10)], top_k)
        return ranked[:top_k]
