"""用临时库和虚构档案验证当前 LLM 配置；会发起一次真实模型调用。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def main() -> None:
    configured = Settings()
    if configured.auth_mode != "local" or configured.llm_provider != "openai":
        raise SystemExit("此实验要求本地认证与 LLM_PROVIDER=openai")
    with tempfile.TemporaryDirectory() as folder:
        settings = configured.model_copy(update={"database_path": Path(folder) / "smoke.db"})
        client = TestClient(create_app(settings))
        headers = {
            "Authorization": f"Bearer {settings.local_demo_token}",
            "X-Demo-Tenant": "smoke-tenant", "X-Demo-Roles": "archive_reader,archive_writer,legal",
            "X-Demo-Clearance": "restricted",
        }
        fixture = json.loads((Path(__file__).resolve().parents[1] / "eval" / "fixtures.json").read_text(encoding="utf-8"))[0]
        ingest = client.post("/v1/archives", json=fixture, headers=headers)
        ingest.raise_for_status()
        answer = client.post(
            "/v1/chat", json={"question": "提前还款需要提前多少天申请？", "as_of": "2026-10-30"}, headers=headers,
        )
        answer.raise_for_status()
        result = answer.json()
        print("model:", settings.openai_model, "grounded:", result["grounded"], "citations:", len(result["citations"]))
        print(result["answer"])


if __name__ == "__main__":
    main()
