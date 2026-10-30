"""针对已启动的本地服务导入示例合同并发起一次问答。"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import httpx

from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant", default="demo-tenant", help="本地演示租户；档案版本冲突时可换一个租户")
    parser.add_argument("--question", default="你好呀？", help="向档案 Agent 提出的问题")
    args = parser.parse_args()
    settings = Settings()
    headers = {
        "Authorization": f"Bearer {settings.local_demo_token}",
        "X-Demo-Tenant": args.tenant,
        "X-Demo-Roles": "archive_reader,archive_writer,legal",
        "X-Demo-Clearance": "restricted",
    }
    contract = json.loads(Path(__file__).with_name("contract.json").read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        ingest = client.post("/v1/archives", headers=headers, json=contract)
        if ingest.status_code == 409:
            raise SystemExit("该租户下同一档案版本已有不同内容。请提升 contract.json 的 version，或用 --tenant 指定新的演示租户。")
        ingest.raise_for_status()
        print("档案入库：", ingest.json()["doc_id"], "幂等返回：", ingest.json()["idempotent"])
        answer = client.post(
            "/v1/chat", headers=headers,
            json={"question": args.question, "as_of": "2026-10-30"},
        )
        answer.raise_for_status()
        print(json.dumps(answer.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
