import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from order_service.auth import require_administrator, require_customer
from platform_auth import AuthClaims


def _claims(*roles: str) -> AuthClaims:
    now = datetime.now(UTC)
    return AuthClaims(
        subject=uuid4(),
        token_id=uuid4(),
        roles=roles,
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )


def test_order_role_gates_keep_customer_and_administrator_capabilities_separate() -> None:
    assert asyncio.run(require_customer(_claims("customer"))).roles == ("customer",)
    assert asyncio.run(require_administrator(_claims("admin"))).roles == ("admin",)

    with pytest.raises(HTTPException, match="customer role required"):
        asyncio.run(require_customer(_claims("admin")))
    with pytest.raises(HTTPException, match="administrator role required"):
        asyncio.run(require_administrator(_claims("customer")))
