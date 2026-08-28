from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from platform_auth import TokenError, decode_access_token, encode_access_token


def test_access_token_round_trip() -> None:
    subject = uuid4()
    token = encode_access_token(
        subject=subject,
        roles=("customer",),
        secret="a" * 40,
        issuer="issuer",
        audience="audience",
        ttl_seconds=900,
    )

    claims = decode_access_token(token, secret="a" * 40, issuer="issuer", audience="audience")

    assert claims.subject == subject
    assert claims.roles == ("customer",)


def test_access_token_rejects_wrong_secret() -> None:
    token = encode_access_token(
        subject=uuid4(),
        roles=("customer",),
        secret="a" * 40,
        issuer="issuer",
        audience="audience",
        ttl_seconds=900,
    )

    with pytest.raises(TokenError):
        decode_access_token(token, secret="b" * 40, issuer="issuer", audience="audience")


def _signed_access_token(*, issued_at: datetime, expires_at: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "jti": str(uuid4()),
            "roles": ["customer"],
            "token_type": "access",
            "iss": "issuer",
            "aud": "audience",
            "iat": issued_at,
            "exp": expires_at,
        },
        "a" * 40,
        algorithm="HS256",
    )


def test_access_token_allows_two_seconds_of_future_issued_at() -> None:
    now = datetime.now(UTC)
    token = _signed_access_token(
        issued_at=now + timedelta(seconds=2),
        expires_at=now + timedelta(minutes=15),
    )

    claims = decode_access_token(token, secret="a" * 40, issuer="issuer", audience="audience")

    assert claims.roles == ("customer",)


def test_access_token_rejects_issued_at_beyond_clock_skew() -> None:
    now = datetime.now(UTC)
    token = _signed_access_token(
        issued_at=now + timedelta(seconds=10),
        expires_at=now + timedelta(minutes=15),
    )

    with pytest.raises(TokenError):
        decode_access_token(token, secret="a" * 40, issuer="issuer", audience="audience")


def test_access_token_expiry_remains_strict() -> None:
    now = datetime.now(UTC)
    token = _signed_access_token(
        issued_at=now - timedelta(seconds=10),
        expires_at=now - timedelta(seconds=1),
    )

    with pytest.raises(TokenError):
        decode_access_token(token, secret="a" * 40, issuer="issuer", audience="audience")
