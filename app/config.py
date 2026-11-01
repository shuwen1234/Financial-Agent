from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "production"] = "local"
    auth_mode: Literal["local", "jwt"] = "local"
    local_demo_token: str = "example-only"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_jwks_url: str | None = None
    database_path: Path = Path("data/archives.db")
    business_timezone: str = "Asia/Shanghai"
    llm_provider: Literal["extractive", "openai"] = "extractive"
     # 新增：API 接口地址
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str | None = None
    openai_api_key: str | None = None
    prompt_version: str = "v1"
    reranker_mode: Literal["none", "bge"] = "none"
    rerank_min_score: float | None = None
    min_token_overlap: int = Field(default=2, ge=1, le=10)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_retrieval_candidates: int = Field(default=2000, ge=10, le=100000)

    @model_validator(mode="after")
    def validate_modes(self) -> Settings:
        if self.app_env == "production" and self.auth_mode != "jwt":
            raise ValueError("生产环境必须使用 JWT 认证")
        if self.auth_mode == "jwt":
            if not all((self.jwt_issuer, self.jwt_audience, self.jwt_jwks_url)):
                raise ValueError("JWT 模式需要 issuer、audience 和 JWKS URL")
            if self.app_env == "production" and not self.jwt_jwks_url.startswith("https://"):
                raise ValueError("生产 JWKS URL 必须使用 HTTPS")
        if self.llm_provider == "openai" and not all((self.openai_api_key, self.openai_model)):
            raise ValueError("OpenAI 模式需要 OPENAI_API_KEY 和 OPENAI_MODEL")
        try:
            ZoneInfo(self.business_timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("无效的业务时区") from None
        return self

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path if self.database_path.is_absolute() else PROJECT_ROOT / self.database_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
