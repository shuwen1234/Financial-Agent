from __future__ import annotations

import json
import subprocess
import sys

from app.config import PROJECT_ROOT


def ruff_findings(paths: list[str]) -> list[dict]:
    existing = [path for path in paths if (PROJECT_ROOT / path).is_file() and path.endswith(".py")]
    if not existing:
        return []
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "json", *existing],
        cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"ruff 运行失败：{completed.stderr.strip()}")
    return json.loads(completed.stdout or "[]")
