from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError


class TokenError(ValueError):
    """Raised when an access token is invalid or has the wrong purpose."""


@dataclass(frozen=True)
class AuthClaims:
    subject: UUID
    token_id: UUID
    roles: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime


def encode_access_token(
    *,
    subject: UUID,
    roles: tuple[str, ...],
    secret: str,
    issuer: str,
    audience: str,
    ttl_seconds: int,
) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "jti": str(uuid4()),
        "roles": list(roles),
        "token_type": "access",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
) -> AuthClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["sub", "jti", "roles", "token_type", "iat", "exp"]},
        )
    except (InvalidTokenError, ValueError) as exc:
        raise TokenError("invalid access token") from exc

    if payload.get("token_type") != "access":
        raise TokenError("wrong token type")
    try:
        subject = UUID(str(payload["sub"]))
        token_id = UUID(str(payload["jti"]))
        roles = tuple(str(role) for role in payload["roles"])
        issued_at = datetime.fromtimestamp(float(payload["iat"]), tz=UTC)
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise TokenError("invalid access token claims") from exc
    return AuthClaims(subject, token_id, roles, issued_at, expires_at)
