from __future__ import annotations

from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedDocument(ValueError):
    pass


def safe_filename(name: str | None) -> str:
    return PurePath((name or "upload").replace("\\", "/")).name[:255]


def extract_text(filename: str, data: bytes, max_chars: int = 2_000_000) -> str:
    suffix = PurePath(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = data.decode("utf-8-sig")
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(data))
            if len(reader.pages) > 500:
                raise UnsupportedDocument("PDF 页数超过 500")
            parts = []
            total = 0
            for number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                total += len(page_text)
                if total > max_chars:
                    raise UnsupportedDocument("提取文本超过上限")
                parts.append(f"第 {number} 页：\n{page_text}")
            text = "\n\n".join(parts)
        elif suffix == ".docx":
            with ZipFile(BytesIO(data)) as archive:
                if len(archive.infolist()) > 2000 or sum(item.file_size for item in archive.infolist()) > 50_000_000:
                    raise UnsupportedDocument("DOCX 解压后超过上限")
            document = Document(BytesIO(data))
            parts = [p.text for p in document.paragraphs if p.text.strip()]
            for table in document.tables:
                parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
            text = "\n\n".join(parts)
        else:
            raise UnsupportedDocument("仅支持 TXT、PDF、DOCX")
    except (UnicodeDecodeError, BadZipFile, PdfReadError, PackageNotFoundError, ValueError, OSError) as exc:
        if isinstance(exc, UnsupportedDocument):
            raise
        raise UnsupportedDocument("文件无法解析") from exc
    if not text.strip():
        raise UnsupportedDocument("未提取到文字；扫描件需先 OCR")
    if len(text) > max_chars:
        raise UnsupportedDocument("提取文本超过上限")
    return text
