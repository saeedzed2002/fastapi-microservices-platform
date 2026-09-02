import os
from uuid import UUID, uuid4

import httpx
import pytest

from platform_auth import encode_access_token

pytestmark = pytest.mark.e2e

LOCAL_SECRET = "local-development-jwt-secret-change-me-32-bytes"
ISSUER = "fastapi-platform.identity"
AUDIENCE = "fastapi-platform"


def _token(*, subject: UUID, roles: tuple[str, ...] = ("customer",)) -> str:
    return encode_access_token(
        subject=subject,
        roles=roles,
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


def test_customer_address_ownership_and_cart_versioning() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    customer_id, other_customer_id = uuid4(), uuid4()
    customer_headers = {"Authorization": f"Bearer {_token(subject=customer_id)}"}
    other_customer_headers = {"Authorization": f"Bearer {_token(subject=other_customer_id)}"}
    first_variant_id, second_variant_id = uuid4(), uuid4()

    with httpx.Client(timeout=10.0, verify=False) as client:
        profile = client.put(
            f"{base_url}/api/v1/customers/me",
            headers=customer_headers,
            json={"display_name": "Phase Four E2E", "email": "PHASE4@EXAMPLE.COM"},
        )
        profile.raise_for_status()
        assert profile.json()["id"] == str(customer_id)
        assert profile.json()["email"] == "phase4@example.com"

        first_address = client.post(
            f"{base_url}/api/v1/customers/me/addresses",
            headers=customer_headers,
            json={
                "label": "Home",
                "recipient_name": "Phase Four",
                "line1": "1 Test Street",
                "city": "Tehran",
                "postal_code": "1000000000",
                "country_code": "ir",
                "is_default": True,
            },
        )
        first_address.raise_for_status()
        assert first_address.json()["country_code"] == "IR"

        second_address = client.post(
            f"{base_url}/api/v1/customers/me/addresses",
            headers=customer_headers,
            json={
                "label": "Office",
                "recipient_name": "Phase Four",
                "line1": "2 Test Street",
                "city": "Tehran",
                "postal_code": "1000000001",
                "country_code": "ir",
                "is_default": True,
            },
        )
        second_address.raise_for_status()
        addresses = client.get(
            f"{base_url}/api/v1/customers/me/addresses", headers=customer_headers
        )
        addresses.raise_for_status()
        assert [address["id"] for address in addresses.json() if address["is_default"]] == [
            second_address.json()["id"]
        ]
        assert (
            client.patch(
                f"{base_url}/api/v1/customers/me/addresses/{first_address.json()['id']}",
                headers=other_customer_headers,
                json={"city": "Shiraz"},
            ).status_code
            == 404
        )

        initial_cart = client.get(f"{base_url}/api/v1/carts/me", headers=customer_headers)
        initial_cart.raise_for_status()
        assert initial_cart.json()["version"] == 1
        assert initial_cart.json()["items"] == []

        first_add = client.post(
            f"{base_url}/api/v1/carts/me/items",
            headers=customer_headers,
            json={"variant_id": str(first_variant_id), "quantity": 2},
        )
        first_add.raise_for_status()
        assert first_add.json()["version"] == 2

        capped_add = client.post(
            f"{base_url}/api/v1/carts/me/items",
            headers=customer_headers,
            json={"variant_id": str(first_variant_id), "quantity": 99},
        )
        capped_add.raise_for_status()
        assert capped_add.json()["items"][0]["quantity"] == 100

        second_add = client.post(
            f"{base_url}/api/v1/carts/me/items",
            headers=customer_headers,
            json={"variant_id": str(second_variant_id), "quantity": 1},
        )
        second_add.raise_for_status()
        expected_version = second_add.json()["version"]

        consumed = client.post(
            f"{base_url}/api/v1/carts/me/consume",
            headers=customer_headers,
            json={
                "expected_version": expected_version,
                "items": [{"variant_id": str(first_variant_id), "quantity": 40}],
            },
        )
        consumed.raise_for_status()
        quantities = {item["variant_id"]: item["quantity"] for item in consumed.json()["items"]}
        assert quantities == {str(first_variant_id): 60, str(second_variant_id): 1}

        stale_consume = client.post(
            f"{base_url}/api/v1/carts/me/consume",
            headers=customer_headers,
            json={
                "expected_version": expected_version,
                "items": [{"variant_id": str(first_variant_id), "quantity": 1}],
            },
        )
        assert stale_consume.status_code == 409
        assert stale_consume.json()["error"]["code"] == "CONFLICT"

        removed = client.delete(
            f"{base_url}/api/v1/carts/me/items/{second_variant_id}", headers=customer_headers
        )
        removed.raise_for_status()
        assert [item["variant_id"] for item in removed.json()["items"]] == [str(first_variant_id)]

        cleared = client.delete(f"{base_url}/api/v1/carts/me", headers=customer_headers)
        cleared.raise_for_status()
        assert cleared.json()["items"] == []
