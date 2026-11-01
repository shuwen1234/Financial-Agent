from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from openai import OpenAIError
from pydantic import ValidationError

from app.agent.graph import FinancialAgent
from app.agent.nodes import AgentNodes
from app.config import Settings, get_settings
from app.retrieve.rerank import make_reranker
from app.schemas.archive import ArchiveCreate, ArchiveMetadata, Classification
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.archive import ArchiveConflict, ArchiveStore, CandidateLimitExceeded
from app.services.auth import AuthService, Principal, get_principal, require_role
from app.services.llm import make_llm
from app.services.parser import UnsupportedDocument, extract_text, safe_filename
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Financial Archive Agent", version="0.1.0")
    app.state.settings = settings
    app.state.store = ArchiveStore(settings.resolved_database_path, settings.max_retrieval_candidates)
    app.state.auth = AuthService(settings)
    app.state.agent = FinancialAgent(AgentNodes(
        RetrievalService(app.state.store, make_reranker(settings), settings.min_token_overlap), make_llm(settings),
    ))

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(request: Request) -> dict[str, str]:
        if not request.app.state.store.ready():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "数据库不可用")
        return {"status": "ok"}

    @app.post("/v1/archives", response_model=ArchiveMetadata, status_code=status.HTTP_201_CREATED)
    def ingest_archive(payload: ArchiveCreate, request: Request, principal: Principal = Depends(get_principal)) -> ArchiveMetadata:
        require_role(principal, "archive_writer")
        if not principal.can_read(payload.classification, payload.acl_roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "不能写入超出本人密级或角色范围的档案")
        try:
            return request.app.state.store.ingest(principal, payload, uuid.uuid4().hex)
        except ArchiveConflict as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    @app.post("/v1/archives/upload", response_model=ArchiveMetadata, status_code=status.HTTP_201_CREATED)
    async def upload_archive(
        request: Request,
        doc_id: str = Form(...), version: int = Form(...), title: str = Form(...),
        classification: Classification = Form(...), acl_roles: str = Form(...),
        effective_from: date = Form(...), effective_to: date | None = Form(default=None),
        file: UploadFile = File(...), principal: Principal = Depends(get_principal),
    ) -> ArchiveMetadata:
        require_role(principal, "archive_writer")
        data = await file.read(settings.max_upload_bytes + 1)
        await file.close()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "文件超过上传上限")
        filename = safe_filename(file.filename)
        try:
            content = extract_text(filename, data)
            payload = ArchiveCreate(
                doc_id=doc_id, version=version, title=title, classification=classification,
                acl_roles=[role.strip() for role in acl_roles.split(",")],
                effective_from=effective_from, effective_to=effective_to, content=content, source_name=filename,
            )
        except UnsupportedDocument as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
        except ValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors(include_url=False)) from None
        return ingest_archive(payload, request, principal)

    @app.get("/v1/archives/{doc_id}/versions/{version}", response_model=ArchiveMetadata)
    def get_archive(doc_id: str, version: int, request: Request, principal: Principal = Depends(get_principal)) -> ArchiveMetadata:
        require_role(principal, "archive_reader")
        record = request.app.state.store.get_version(principal.tenant_id, doc_id, version)
        if record is None or not principal.can_read(record.classification, record.acl_roles):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "档案不存在")
        request.app.state.store.audit(uuid.uuid4().hex, principal, "archive.metadata", "read", {"doc_id": doc_id, "version": version})
        return ArchiveMetadata(**record.model_dump(exclude={"content"}))

    @app.post("/v1/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest, request: Request, principal: Principal = Depends(get_principal)) -> ChatResponse:
        require_role(principal, "archive_reader")
        as_of = payload.as_of or datetime.now(ZoneInfo(settings.business_timezone)).date()
        trace_id = uuid.uuid4().hex
        try:
            state = request.app.state.agent.run(principal, payload.question, as_of, payload.top_k)
        except CandidateLimitExceeded as exc:
            request.app.state.store.audit(trace_id, principal, "archive.query", "candidate_limit", {})
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
        except OpenAIError:
            request.app.state.store.audit(trace_id, principal, "archive.query", "llm_error", {})
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "模型服务暂时不可用") from None
        citations = state["citations"]
        request.app.state.store.audit(
            trace_id, principal, "archive.query", "answered" if state["grounded"] else "insufficient_evidence",
            {"question_sha256": hashlib.sha256(payload.question.encode("utf-8")).hexdigest(),
             "references": [{"doc_id": c.doc_id, "version": c.version} for c in citations]},
        )
        return ChatResponse(trace_id=trace_id, answer=state["answer"], grounded=state["grounded"],
                            citations=citations, retrieval_attempts=state["attempts"], as_of=as_of,
                            plan=state["plan"])

    @app.post("/v1/chat/stream")
    async def chat_stream(payload: ChatRequest, request: Request, principal: Principal = Depends(get_principal)) -> StreamingResponse:
        require_role(principal, "archive_reader")
        as_of = payload.as_of or datetime.now(ZoneInfo(settings.business_timezone)).date()
        trace_id = uuid.uuid4().hex

        async def events():
            final: dict = {}
            try:
                async for update in request.app.state.agent.stream_updates(principal, payload.question, as_of, payload.top_k):
                    if await request.is_disconnected():
                        request.app.state.store.audit(trace_id, principal, "archive.query", "cancelled", {})
                        logger.warning("已取消 trace_id=%s", trace_id)
                        return
                    for node, values in update.items():
                        final.update(values)
                        if node == "plan":
                            yield sse("plan", {"trace_id": trace_id, "steps": values["plan"]})
                        elif node == "retrieve":
                            yield sse("retrieve", {"attempts": values["attempts"], "count": len(values["evidence"])})
                        elif node == "grade":
                            yield sse("grade", {"sufficient": values["sufficient"]})
                        elif node == "rewrite":
                            yield sse("rewrite", {"attempts": final.get("attempts", 0)})
                        elif node == "synthesize":
                            answer = values["answer"]
                            for start in range(0, len(answer), 16):
                                if await request.is_disconnected():
                                    request.app.state.store.audit(trace_id, principal, "archive.query", "cancelled", {})
                                    logger.warning("已取消 trace_id=%s", trace_id)
                                    return
                                yield sse("token", {"text": answer[start:start + 16]})
                            yield sse("citation", {"sources": [c.model_dump(mode="json") for c in values["citations"]]})
                request.app.state.store.audit(
                    trace_id, principal, "archive.query", "answered" if final.get("grounded") else "insufficient_evidence",
                    {"question_sha256": hashlib.sha256(payload.question.encode("utf-8")).hexdigest(),
                     "references": [{"doc_id": c.doc_id, "version": c.version} for c in final.get("citations", [])]},
                )
                yield sse("done", {"trace_id": trace_id, "grounded": final.get("grounded", False)})
            except asyncio.CancelledError:
                logger.warning("已取消 trace_id=%s", trace_id)
                request.app.state.store.audit(trace_id, principal, "archive.query", "cancelled", {})
                raise
            except (CandidateLimitExceeded, OpenAIError):
                request.app.state.store.audit(trace_id, principal, "archive.query", "error", {})
                yield sse("error", {"trace_id": trace_id, "message": "检索或模型服务暂时不可用"})

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()
