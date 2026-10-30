from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rank_bm25 import BM25Okapi

from app.services.archive import ArchiveStore, CandidateLimitExceeded
from app.services.auth import Principal


@dataclass(frozen=True)
class Evidence:
    doc_id: str
    version: int
    title: str
    excerpt: str
    score: float


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", text.lower()):
        word = match.group()
        if "\u4e00" <= word[0] <= "\u9fff":
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


def chunks(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    result: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= size:
            result.append(paragraph)
        else:
            step = size - overlap
            result.extend(paragraph[start:start + size] for start in range(0, len(paragraph), step))
    return result


class RetrievalService:
    def __init__(self, store: ArchiveStore):
        self.store = store

    def search(self, principal: Principal, question: str, as_of: date, top_k: int) -> list[Evidence]:
        records = [r for r in self.store.list_effective(principal.tenant_id, as_of) if principal.can_read(r.classification, r.acl_roles)]
        candidates = []
        for record in records:
            for chunk in chunks(record.content):
                if tokenize(chunk):
                    candidates.append((record, chunk))
                    if len(candidates) > self.store.max_candidates * 5:
                        raise CandidateLimitExceeded("候选片段超过本地检索上限，请切换索引服务")
        if not candidates:
            return []
        token_lists = [tokenize(chunk) for _, chunk in candidates]
        query_tokens = tokenize(question)
        if not query_tokens:
            return []
        bm25_scores = BM25Okapi(token_lists).get_scores(query_tokens)
        query_set = set(query_tokens)
        ranked: list[Evidence] = []
        for (record, chunk), doc_tokens, bm25_score in zip(candidates, token_lists, bm25_scores):
            overlap = len(query_set.intersection(doc_tokens))
            if overlap == 0:
                continue
            score = float(bm25_score) + overlap
            ranked.append(Evidence(record.doc_id, record.version, record.title, chunk[:600], round(score, 4)))
        ranked.sort(key=lambda x: (-x.score, x.doc_id, -x.version))
        return ranked[:top_k]
