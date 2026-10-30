from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(_env_file=None, database_path=tmp_path / "archives.db", app_env="local", auth_mode="local", llm_provider="extractive")
    return TestClient(create_app(settings))


def headers(tenant: str = "tenant-a", roles: str = "archive_reader,archive_writer,legal", clearance: str = "restricted") -> dict[str, str]:
    return {"Authorization": "Bearer example-only", "X-Demo-Tenant": tenant, "X-Demo-Roles": roles, "X-Demo-Clearance": clearance}


def archive(version: int = 1, content: str = "第七条：提前还款需提前三十天提交书面申请。", effective_from: str = "2026-01-01") -> dict:
    return {
        "doc_id": "CONTRACT-001", "version": version, "title": "贷款合同示例",
        "classification": "confidential", "acl_roles": ["legal"],
        "effective_from": effective_from, "content": content,
    }


def test_ingest_idempotency_and_conflict(client: TestClient) -> None:
    first = client.post("/v1/archives", headers=headers(), json=archive())
    assert first.status_code == 201 and first.json()["idempotent"] is False
    again = client.post("/v1/archives", headers=headers(), json=archive())
    assert again.status_code == 201 and again.json()["idempotent"] is True
    changed = client.post("/v1/archives", headers=headers(), json=archive(content="另一份内容"))
    assert changed.status_code == 409


def test_chat_filters_tenant_clearance_and_date(client: TestClient) -> None:
    assert client.post("/v1/archives", headers=headers(), json=archive()).status_code == 201
    payload = {"question": "提前还款需要提前几天申请？", "as_of": "2026-10-30"}
    good = client.post("/v1/chat", headers=headers(), json=payload)
    assert good.status_code == 200
    assert good.json()["grounded"] is True
    assert good.json()["citations"][0]["doc_id"] == "CONTRACT-001"
    for filtered_headers, filtered_payload in [
        (headers(tenant="tenant-b"), payload),
        (headers(clearance="internal"), payload),
        (headers(roles="archive_reader,finance"), payload),
        (headers(), {**payload, "as_of": "2025-12-31"}),
    ]:
        result = client.post("/v1/chat", headers=filtered_headers, json=filtered_payload)
        assert result.status_code == 200
        assert result.json()["grounded"] is False
        assert result.json()["citations"] == []


def test_latest_effective_version_and_upload(client: TestClient) -> None:
    client.post("/v1/archives", headers=headers(), json=archive())
    client.post("/v1/archives", headers=headers(), json=archive(version=2, content="新版：提前还款需提前十五天申请。", effective_from="2026-06-01"))
    result = client.post("/v1/chat", headers=headers(), json={"question": "提前还款需要提前几天申请？", "as_of": "2026-10-30"})
    assert result.json()["citations"][0]["version"] == 2
    upload = client.post(
        "/v1/archives/upload", headers=headers(),
        data={"doc_id": "POLICY-001", "version": "1", "title": "合规政策", "classification": "internal",
              "acl_roles": "legal", "effective_from": "2026-01-01"},
        files={"file": ("policy.txt", "反洗钱审查应核验客户身份。".encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 201
    assert upload.json()["source_name"] == "policy.txt"


def test_auth_and_audit_privacy(client: TestClient) -> None:
    assert client.post("/v1/chat", json={"question": "合同条款是什么？"}).status_code == 401
    query = "包含客户敏感信息的合同问题"
    client.post("/v1/chat", headers=headers(), json={"question": query, "as_of": "2026-10-30"})
    with sqlite3.connect(client.app.state.store.path) as conn:
        details = conn.execute("SELECT details_json FROM audit_events WHERE action='archive.query'").fetchone()[0]
    assert query not in details
    assert json.loads(details)["question_sha256"]


def test_production_rejects_local_auth() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", auth_mode="local")
