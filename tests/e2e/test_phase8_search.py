import os
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import httpx
import pytest

from platform_auth import encode_access_token

pytestmark = pytest.mark.e2e

LOCAL_SECRET = "local-development-jwt-secret-change-me-32-bytes"
ISSUER = "fastapi-platform.identity"
AUDIENCE = "fastapi-platform"


def _token(*, subject: str, roles: tuple[str, ...]) -> str:
    return encode_access_token(
        subject=UUID(subject),
        roles=roles,
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


def _wait_for(predicate: Callable[[], bool], *, timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for Search projection state")


def test_catalog_events_drive_public_search_projection() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    suffix = uuid4().hex[:12]
    initial_query = f"phaseeightinitial{suffix}"
    updated_query = f"phaseeightupdated{suffix}"
    administrator_headers = {
        "Authorization": f"Bearer {_token(subject=str(uuid4()), roles=('admin',))}"
    }
    customer_headers = {
        "Authorization": f"Bearer {_token(subject=str(uuid4()), roles=('customer',))}"
    }

    with httpx.Client(timeout=10.0, verify=False) as client:
        product = client.post(
            f"{base_url}/api/v1/catalog/products",
            headers=administrator_headers,
            json={
                "name": initial_query,
                "slug": f"phase-eight-search-{suffix}",
                "description": "Catalog event projection E2E test",
                "price_amount": "125000.00",
                "currency": "IRT",
                "attributes": {"color": "black"},
            },
        )
        product.raise_for_status()
        product_id = product.json()["id"]

        def search(query: str) -> list[dict[str, object]]:
            response = client.get(f"{base_url}/api/v1/search/products", params={"q": query})
            response.raise_for_status()
            return response.json()["items"]

        assert all(item["product_id"] != product_id for item in search(initial_query))

        client.post(
            f"{base_url}/api/v1/catalog/products/{product_id}/publish",
            headers=administrator_headers,
        ).raise_for_status()

        def published_product_is_searchable() -> bool:
            return any(item["product_id"] == product_id for item in search(initial_query))

        _wait_for(published_product_is_searchable)

        client.patch(
            f"{base_url}/api/v1/catalog/products/{product_id}",
            headers=administrator_headers,
            json={"name": updated_query},
        ).raise_for_status()

        def updated_product_is_searchable() -> bool:
            return any(item["product_id"] == product_id for item in search(updated_query))

        _wait_for(updated_product_is_searchable)
        assert all(item["product_id"] != product_id for item in search(initial_query))

        assert (
            client.delete(
                f"{base_url}/api/v1/catalog/products/{product_id}",
                headers=customer_headers,
            ).status_code
            == 403
        )
        client.delete(
            f"{base_url}/api/v1/catalog/products/{product_id}",
            headers=administrator_headers,
        ).raise_for_status()

        def deleted_product_is_not_searchable() -> bool:
            return all(item["product_id"] != product_id for item in search(updated_query))

        _wait_for(deleted_product_is_not_searchable)
