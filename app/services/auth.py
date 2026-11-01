from __future__ import annotations

import hmac
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import PyJWKClient

from app.config import Settings
from app.schemas.archive import CLASSIFICATION_LEVEL, Classification


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: frozenset[str]
    clearance: Classification

    def can_read(self, classification: Classification, acl_roles: list[str]) -> bool:
        return (
            CLASSIFICATION_LEVEL[self.clearance] >= CLASSIFICATION_LEVEL[classification]
            and bool(self.roles.intersection(acl_roles))
        )


class AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.jwt_jwks_url, cache_keys=True) if settings.auth_mode == "jwt" else None

    def authenticate(self, authorization: str | None, demo_tenant: str | None, demo_user: str | None, demo_roles: str | None, demo_clearance: str | None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少 Bearer Token")
        token = authorization.removeprefix("Bearer ").strip()
        if self.settings.auth_mode == "local":
            if not hmac.compare_digest(token, self.settings.local_demo_token):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "认证失败")
            roles = frozenset(x.strip() for x in (demo_roles or "archive_reader,archive_writer,legal").split(",") if x.strip())
            try:
                clearance = Classification(demo_clearance or "restricted")
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "无效的演示密级") from None
            return Principal(demo_user or "local-user", demo_tenant or "demo-tenant", roles, clearance)

        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, signing_key, algorithms=["RS256"], audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "iat", "sub", "tenant_id", "roles", "clearance"]},
            )
            roles = claims.get("roles", [])
            if not isinstance(roles, list) or not all(isinstance(x, str) for x in roles):
                raise ValueError("invalid roles")
            if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("tenant_id"), str):
                raise TypeError("invalid subject or tenant")
            principal = Principal(
                user_id=claims["sub"],
                tenant_id=claims["tenant_id"],
                roles=frozenset(roles),
                clearance=Classification(claims["clearance"]),
            )
            if not principal.user_id or not principal.tenant_id:
                raise ValueError("empty subject or tenant")
            return principal
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "认证失败") from None


def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_demo_tenant: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
    x_demo_roles: str | None = Header(default=None),
    x_demo_clearance: str | None = Header(default=None),
) -> Principal:
    if request.app.state.settings.auth_mode == "local" and (request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "本地演示模式只接受本机请求")
    return request.app.state.auth.authenticate(authorization, x_demo_tenant, x_demo_user, x_demo_roles, x_demo_clearance)


def require_role(principal: Principal, role: str) -> None:
    if role not in principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
