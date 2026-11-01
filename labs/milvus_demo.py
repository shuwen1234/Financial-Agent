"""Milvus Lite：50 子块、1024 维向量、权限标量过滤、upsert 与按 doc_id 删除。"""
from __future__ import annotations

import argparse
import hashlib
import math
import re
from pathlib import Path

from app.config import PROJECT_ROOT

TOPICS = [
    "提前还款需要查看合同约定", "违约责任应依据合同条款", "客户身份识别属于反洗钱审查",
    "合同变更需要保留书面记录", "档案生效日期决定条款适用", "投资产品存在风险",
    "账户注销需要核验身份", "合规检查记录应当留存", "贷款利率以合同为准", "档案权限按部门和密级控制",
]


def hash_vector(text: str, dimension: int = 1024) -> list[float]:
    """离线流程向量；不是语义模型，不能用它评估检索质量。"""
    values = [0.0] * dimension
    chars = re.sub(r"\s+", "", text)
    for start in range(max(1, len(chars) - 1)):
        token = chars[start:start + 2]
        digest = hashlib.sha256(token.encode()).digest()
        values[int.from_bytes(digest[:4], "big") % dimension] += 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def run(uri: str, real_model: bool, scope: str) -> None:
    from pymilvus import DataType, MilvusClient

    if not uri.startswith(("http://", "https://")):
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
    texts = [f"{topic}。第 {repeat + 1} 份示例说明。" for topic in TOPICS for repeat in range(5)]
    questions = ["提前还款的合同约定是什么？", "客户身份如何核验？", "谁能访问合规档案？"]
    if real_model:
        from FlagEmbedding import BGEM3FlagModel

        model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        vectors = model.encode(texts, batch_size=8)["dense_vecs"].tolist()
        query_vectors = model.encode(questions)["dense_vecs"].tolist()
    else:
        vectors = [hash_vector(text) for text in texts]
        query_vectors = [hash_vector(question) for question in questions]
    assert len(vectors[0]) == 1024

    client = MilvusClient(uri=uri)
    collection = "financial_lab_chunks"
    if not client.has_collection(collection):
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="parent_id", datatype=DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="dept_scope", datatype=DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=1000)
        index = client.prepare_index_params()
        index.add_index(field_name="vector", index_type="FLAT", metric_type="COSINE")
        client.create_collection(collection_name=collection, schema=schema, index_params=index)
    rows = [
        {"chunk_id": i, "vector": vector, "doc_id": f"DOC-{i // 5:02d}",
         "parent_id": f"P-{i // 5:02d}", "dept_scope": "all" if i % 2 == 0 else "legal", "text": text}
        for i, (vector, text) in enumerate(zip(vectors, texts))
    ]
    client.upsert(collection_name=collection, data=rows)
    client.load_collection(collection_name=collection)
    print("collection:", collection, "rows:", len(rows), "vector_dim:", len(vectors[0]))
    allowed_scopes = ["all"] if scope == "all" else ["all", "legal"]
    filter_expr = "dept_scope in [" + ", ".join(repr(value) for value in allowed_scopes) + "]"
    print("scalar filter:", filter_expr)
    for question, vector in zip(questions, query_vectors):
        hits = client.search(
            collection_name=collection, data=[vector], limit=5,
            filter=filter_expr, output_fields=["doc_id", "parent_id", "dept_scope", "text"],
        )[0]
        print("问题:", question)
        for hit in hits:
            print(hit["chunk_id"], round(hit["distance"], 4), hit["entity"])
    deleted = client.delete(collection_name=collection, filter="doc_id == 'DOC-09'")
    print("按 doc_id 删除演示:", deleted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=str(PROJECT_ROOT / "data" / "milvus_lab.db"))
    parser.add_argument("--real-model", action="store_true", help="下载并运行 BGE-M3，首次较慢")
    parser.add_argument("--scope", choices=["all", "legal"], default="all", help="比较部门标量过滤效果")
    args = parser.parse_args()
    run(args.uri, args.real_model, args.scope)
