from __future__ import annotations

import os

import pytest

from app.prompts.loader import PromptRegistry


def test_prompt_version_variables_and_reload(tmp_path) -> None:
    folder = tmp_path / "answer"
    folder.mkdir()
    source = folder / "v1.yaml"
    source.write_text(
        "name: answer\nversion: v1\nvariables: [question, evidence]\nsystem: '版本一'\nuser: '{{ question }} | {{ evidence }}'\n",
        encoding="utf-8",
    )
    registry = PromptRegistry(tmp_path)
    assert registry.render("answer", "v1", question="问题", evidence="证据") == ("版本一", "问题 | 证据")
    with pytest.raises(ValueError):
        registry.render("answer", "v1", question="缺少证据")
    previous = source.stat().st_mtime_ns
    source.write_text(
        "name: answer\nversion: v1\nvariables: [question, evidence]\nsystem: '版本一已更新'\nuser: '{{ question }} | {{ evidence }}'\n",
        encoding="utf-8",
    )
    os.utime(source, ns=(previous + 1_000_000_000, previous + 1_000_000_000))
    assert registry.render("answer", "v1", question="问题", evidence="证据")[0] == "版本一已更新"
