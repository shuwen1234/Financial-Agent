"""按段落/章节建立父块，再按字符窗口建立检索子块。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

HEADING = re.compile(r"^(?:#{1,6}\s+|第[一二三四五六七八九十百千万0-9]+[章节条款])")


@dataclass(frozen=True)
class ChildChunk:
    child_id: str
    parent_id: str
    text: str
    parent_text: str
    section_path: str


def build_chunks(text: str, child_size: int = 200, overlap: int = 30) -> list[ChildChunk]:
    if not 0 <= overlap < child_size:
        raise ValueError("overlap 必须小于 child_size")
    sections: list[str] = []
    result: list[ChildChunk] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    for parent_index, paragraph in enumerate(paragraphs):
        first_line = paragraph.splitlines()[0].strip()
        if HEADING.match(first_line):
            if first_line.startswith("#"):
                level = len(first_line) - len(first_line.lstrip("#"))
                sections = sections[:level - 1] + [first_line.lstrip("# ")]
            else:
                sections = [first_line[:80]]
        section_path = " / ".join(sections) or "正文"
        parent_id = hashlib.sha256(f"{parent_index}:{section_path}:{paragraph}".encode()).hexdigest()[:16]
        step = child_size - overlap
        for start in range(0, len(paragraph), step):
            child = paragraph[start:start + child_size]
            if not child:
                continue
            child_id = f"{parent_id}:{start}"
            result.append(ChildChunk(child_id, parent_id, child, paragraph, section_path))
            if start + child_size >= len(paragraph):
                break
    return result
