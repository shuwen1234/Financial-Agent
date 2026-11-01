from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.config import Settings
from app.services.auth import AuthService


def test_production_jwt_verifies_signature_claims_and_expiry() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        _env_file=None, app_env="production", auth_mode="jwt",
        jwt_issuer="https://issuer.example", jwt_audience="financial-agent",
        jwt_jwks_url="https://issuer.example/jwks",
    )
    auth = AuthService(settings)
    auth.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key()))
    now = datetime.now(UTC)
    claims = {
        "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
        "sub": "user-1", "tenant_id": "tenant-a", "roles": ["archive_reader", "legal"],
        "clearance": "confidential", "iat": now, "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    principal = auth.authenticate(f"Bearer {token}", None, None, None, None)
    assert principal.tenant_id == "tenant-a" and "legal" in principal.roles
    with pytest.raises(HTTPException) as expired:
        auth.authenticate(f"Bearer {jwt.encode({**claims, 'exp': now - timedelta(minutes=1)}, private_key, algorithm='RS256')}", None, None, None, None)
    assert expired.value.status_code == 401
    without_exp = {key: value for key, value in claims.items() if key != "exp"}
    with pytest.raises(HTTPException) as missing:
        auth.authenticate(f"Bearer {jwt.encode(without_exp, private_key, algorithm='RS256')}", None, None, None, None)
    assert missing.value.status_code == 401
