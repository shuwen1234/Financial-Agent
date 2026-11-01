"""保留 Word 标题层级与表格文本的轻量解析。"""
from __future__ import annotations

from io import BytesIO

from docx import Document


def extract_docx(data: bytes) -> str:
    document = Document(BytesIO(data))
    parts: list[str] = []
    for paragraph in document.paragraphs:
        value = paragraph.text.strip()
        if not value:
            continue
        style = paragraph.style.name.lower() if paragraph.style else ""
        if style.startswith(("heading", "标题")):
            digits = "".join(ch for ch in style if ch.isdigit())
            level = min(int(digits), 6) if digits else 1
            value = f"{'#' * level} {value}"
        parts.append(value)
    for table_index, table in enumerate(document.tables, start=1):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        parts.append(f"表格 {table_index}\n" + "\n".join(rows))
    return "\n\n".join(parts)
