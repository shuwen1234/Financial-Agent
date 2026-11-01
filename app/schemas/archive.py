from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Classification(str, Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


CLASSIFICATION_LEVEL = {x: i for i, x in enumerate(Classification)}


class ArchiveCreate(BaseModel):
    doc_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    classification: Classification
    acl_roles: list[str] = Field(min_length=1, max_length=20)
    effective_from: date
    effective_to: date | None = None
    content: str = Field(min_length=1, max_length=2_000_000)
    source_name: str | None = Field(default=None, max_length=255)

    @field_validator("acl_roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        if any(not role or len(role) > 64 or not role.replace("_", "").replace("-", "").isalnum() for role in roles):
            raise ValueError("acl_roles 只能包含简短的角色名")
        return sorted(set(roles))

    @model_validator(mode="after")
    def validate_dates(self) -> ArchiveCreate:
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to 不能早于 effective_from")
        return self


class ArchiveMetadata(BaseModel):
    tenant_id: str
    doc_id: str
    version: int
    title: str
    classification: Classification
    acl_roles: list[str]
    effective_from: date
    effective_to: date | None
    source_name: str | None
    checksum: str
    created_at: datetime
    idempotent: bool = False


class StoredArchive(ArchiveMetadata):
    content: str
