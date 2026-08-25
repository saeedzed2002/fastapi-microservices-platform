from uuid import uuid4

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
