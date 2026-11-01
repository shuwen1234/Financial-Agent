from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from app.schemas.archive import ArchiveCreate, ArchiveMetadata, StoredArchive
from app.services.auth import Principal


class ArchiveConflict(Exception):
    pass


class CandidateLimitExceeded(Exception):
    pass


class ArchiveStore:
    def __init__(self, path: Path, max_candidates: int):
        self.path = path
        self.max_candidates = max_candidates
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS archives (
                    tenant_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    acl_roles TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    content TEXT NOT NULL,
                    source_name TEXT,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, doc_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_archives_effective
                    ON archives(tenant_id, effective_from, effective_to);
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    occurred_at TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
            """)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredArchive:
        return StoredArchive(
            tenant_id=row["tenant_id"], doc_id=row["doc_id"], version=row["version"], title=row["title"],
            classification=row["classification"], acl_roles=json.loads(row["acl_roles"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"], content=row["content"],
            source_name=row["source_name"], checksum=row["checksum"], created_at=row["created_at"],
        )

    def ingest(self, principal: Principal, payload: ArchiveCreate, trace_id: str) -> ArchiveMetadata:
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode("utf-8")
        checksum = hashlib.sha256(canonical).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM archives WHERE tenant_id=? AND doc_id=? AND version=?",
                (principal.tenant_id, payload.doc_id, payload.version),
            ).fetchone()
            if existing:
                if existing["checksum"] != checksum:
                    raise ArchiveConflict("该档案版本已存在，内容或元数据不同")
                record = self._from_row(existing)
                idempotent = True
            else:
                conn.execute(
                    """INSERT INTO archives (tenant_id,doc_id,version,title,classification,acl_roles,effective_from,effective_to,content,source_name,checksum,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (principal.tenant_id, payload.doc_id, payload.version, payload.title, payload.classification.value,
                     json.dumps(payload.acl_roles), payload.effective_from.isoformat(),
                     payload.effective_to.isoformat() if payload.effective_to else None, payload.content,
                     payload.source_name, checksum, now),
                )
                record = StoredArchive(tenant_id=principal.tenant_id, checksum=checksum, created_at=now, **payload.model_dump())
                idempotent = False
            self._audit_in_transaction(conn, trace_id, principal, "archive.ingest", "ok", {"doc_id": payload.doc_id, "version": payload.version, "idempotent": idempotent})
            return ArchiveMetadata(**record.model_dump(exclude={"content", "idempotent"}), idempotent=idempotent)

    def list_effective(self, tenant_id: str, as_of: date) -> list[StoredArchive]:
        day = as_of.isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT * FROM archives WHERE tenant_id=? AND effective_from<=?
                   AND (effective_to IS NULL OR effective_to>=?)
                   ORDER BY doc_id, version DESC LIMIT ?""",
                (tenant_id, day, day, self.max_candidates + 1),
            ).fetchall()
        if len(rows) > self.max_candidates:
            raise CandidateLimitExceeded("候选档案超过本地检索上限，请切换索引服务")
        latest: dict[str, StoredArchive] = {}
        for row in rows:
            if row["doc_id"] not in latest:
                latest[row["doc_id"]] = self._from_row(row)
        return list(latest.values())

    def get_version(self, tenant_id: str, doc_id: str, version: int) -> StoredArchive | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM archives WHERE tenant_id=? AND doc_id=? AND version=?",
                (tenant_id, doc_id, version),
            ).fetchone()
        return self._from_row(row) if row else None

    def audit(self, trace_id: str, principal: Principal, action: str, outcome: str, details: dict) -> None:
        with self._connection() as conn:
            self._audit_in_transaction(conn, trace_id, principal, action, outcome, details)

    @staticmethod
    def _audit_in_transaction(conn: sqlite3.Connection, trace_id: str, principal: Principal, action: str, outcome: str, details: dict) -> None:
        conn.execute(
            "INSERT INTO audit_events(occurred_at,trace_id,tenant_id,user_id,action,outcome,details_json) VALUES(?,?,?,?,?,?,?)",
            (datetime.now(UTC).isoformat(), trace_id, principal.tenant_id, principal.user_id,
             action, outcome, json.dumps(details, ensure_ascii=False, sort_keys=True)),
        )

    def ready(self) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
