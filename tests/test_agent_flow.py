from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.parse.chunker import build_chunks


def test_parent_child_chunks_preserve_section() -> None:
    text = "# 合同条款\n\n" + "提前还款需提交书面申请。" * 30
    children = build_chunks(text, child_size=80, overlap=10)
    body = [child for child in children if "提前还款" in child.text]
    assert len(body) > 1
    assert len({child.parent_id for child in body}) == 1
    assert all(child.section_path == "合同条款" for child in body)


def test_stream_emits_graph_events_and_grounded_citation(tmp_path) -> None:
    app = create_app(Settings(_env_file=None, database_path=tmp_path / "archive.db", llm_provider="extractive"))
    client = TestClient(app)
    headers = {
        "Authorization": "Bearer example-only", "X-Demo-Tenant": "team-a",
        "X-Demo-Roles": "archive_reader,archive_writer,legal", "X-Demo-Clearance": "restricted",
    }
    payload = {
        "doc_id": "CONTRACT-001", "version": 1, "title": "测试合同", "classification": "internal",
        "acl_roles": ["legal"], "effective_from": "2026-01-01",
        "content": "# 合同条款\n\n第七条 提前还款需提前三十日提交书面申请。",
    }
    assert client.post("/v1/archives", headers=headers, json=payload).status_code == 201
    response = client.post(
        "/v1/chat/stream", headers=headers,
        json={"question": "提前还钱需要提前多少天申请？", "as_of": "2026-10-30"},
    )
    assert response.status_code == 200
    for event in ("plan", "retrieve", "grade", "token", "citation", "done"):
        assert f"event: {event}" in response.text
    assert "CONTRACT-001" in response.text
    assert '"grounded": true' in response.text
