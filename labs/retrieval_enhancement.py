"""Multi-Query、术语归一、HyDE 的离线/真实模型对照。"""
from __future__ import annotations

import argparse
import math

from pydantic import BaseModel, Field

from app.config import Settings
from app.retrieve.glossary import normalize_query
from labs.milvus_demo import TOPICS, hash_vector


class QueryVariants(BaseModel):
    queries: list[str] = Field(min_length=3, max_length=3)


def model_text(settings: Settings, prompt: str, structured: bool = False):
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=30)
    if structured:
        return client.responses.parse(model=settings.openai_model, input=prompt, text_format=QueryVariants).output_parsed
    return client.responses.create(model=settings.openai_model, input=prompt).output_text


def vectorize(texts: list[str], real_model: bool) -> list[list[float]]:
    if real_model:
        from FlagEmbedding import BGEM3FlagModel

        return BGEM3FlagModel("BAAI/bge-m3", use_fp16=False).encode(texts)["dense_vecs"].tolist()
    return [hash_vector(text) for text in texts]


def rank(vector: list[float], corpus_vectors: list[list[float]]) -> list[int]:
    return sorted(range(len(corpus_vectors)), key=lambda i: sum(a * b for a, b in zip(vector, corpus_vectors[i])), reverse=True)[:5]


def run(real_model: bool, use_llm: bool) -> None:
    question = "提前还钱需要走什么流程？"
    settings = Settings()
    if use_llm:
        if not settings.openai_api_key or not settings.openai_model:
            raise ValueError("--use-llm 需要配置模型与密钥")
        variants = model_text(settings, f"把这个问题改写成三个不同的档案检索查询，只返回 queries 字段：{question}", structured=True)
        queries = variants.queries
        hypothetical = model_text(settings, f"为检索写一段假设性合同段落，不要声称它是真实条款：{question}")
    else:
        queries = [question, normalize_query(question), "提前还款 申请 流程"]
        hypothetical = "合同约定提前还款时，借款人需提交申请并核对办理流程。"
        print("当前是离线改写与假设段落；--use-llm 才调用模型。")
    corpus = [f"{topic}。" for topic in TOPICS]
    vectors = vectorize(corpus + [question, hypothetical] + queries, real_model)
    corpus_vectors = vectors[:len(corpus)]
    question_vector = vectors[len(corpus)]
    hypothetical_vector = vectors[len(corpus) + 1]
    query_vectors = vectors[len(corpus) + 2:]
    mixed = [0.6 * a + 0.4 * b for a, b in zip(hypothetical_vector, question_vector)]
    norm = math.sqrt(sum(x * x for x in mixed)) or 1.0
    mixed = [x / norm for x in mixed]
    print("原问题 top5:", rank(question_vector, corpus_vectors))
    print("Multi-Query:", queries)
    print("各查询 top5:", [rank(v, corpus_vectors) for v in query_vectors])
    print("HyDE 加权 top5:", rank(mixed, corpus_vectors))
    print("假设段落仅用于检索，不作为回答依据:", hypothetical)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-model", action="store_true", help="使用 BGE-M3，需安装 FlagEmbedding")
    parser.add_argument("--use-llm", action="store_true", help="模型生成三个查询及 HyDE 段落")
    args = parser.parse_args()
    run(args.real_model, args.use_llm)
