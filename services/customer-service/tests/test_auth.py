import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from customer_service.auth import require_customer
from platform_auth import AuthClaims


def test_customer_profile_access_requires_customer_role() -> None:
    now = datetime.now(UTC)
    administrator = AuthClaims(
        subject=uuid4(),
        token_id=uuid4(),
        roles=("admin",),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    with pytest.raises(HTTPException, match="customer role required"):
        asyncio.run(require_customer(administrator))
