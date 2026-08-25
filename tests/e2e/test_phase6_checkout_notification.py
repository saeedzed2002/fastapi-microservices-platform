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
        result = predicate()
        if result:
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for E2E workflow state")


def test_checkout_generates_invoice_and_sends_notification() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    import boto3

    base_url = os.environ.get("E2E_BASE_URL", "http://localhost")
    user_id, admin_id = str(uuid4()), str(uuid4())
    user_headers = {"Authorization": f"Bearer {_token(subject=user_id, roles=('customer',))}"}
    admin_token = _token(subject=admin_id, roles=("admin", "catalog_admin", "inventory_admin"))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    suffix = uuid4().hex[:12]
    sku = f"P6-{suffix}"

    with httpx.Client(timeout=10.0) as client:
        client.put(
            f"{base_url}:8002/api/v1/customers/me",
            headers=user_headers,
            json={"display_name": "Phase Six E2E"},
        ).raise_for_status()
        address = client.post(
            f"{base_url}:8002/api/v1/customers/me/addresses",
            headers=user_headers,
            json={
                "label": "Test",
                "recipient_name": "Phase Six",
                "line1": "1 Test Street",
                "city": "Tehran",
                "postal_code": "1000000000",
                "country_code": "IR",
                "is_default": True,
            },
        )
        address.raise_for_status()
        product = client.post(
            f"{base_url}:8003/api/v1/catalog/products",
            headers=admin_headers,
            json={
                "name": f"Phase 6 {suffix}",
                "slug": f"phase-6-{suffix}",
                "description": "Invoice E2E test",
                "price_amount": "12.50",
                "currency": "USD",
                "attributes": {},
            },
        )
        product.raise_for_status()
        product_id = product.json()["id"]
        variant = client.post(
            f"{base_url}:8003/api/v1/catalog/products/{product_id}/variants",
            headers=admin_headers,
            json={"sku": sku, "name": "Default", "attributes": {}},
        )
        variant.raise_for_status()
        client.post(
            f"{base_url}:8003/api/v1/catalog/products/{product_id}/publish",
            headers=admin_headers,
        ).raise_for_status()
        client.post(
            f"{base_url}:8005/api/v1/inventory/stock-items",
            headers=admin_headers,
            json={"sku": sku, "initial_quantity": 2},
        ).raise_for_status()
        previous_messages = len(client.get(f"{base_url}:8025/api/v1/messages").json()["messages"])
        order = client.post(
            f"{base_url}:8007/api/v1/orders",
            headers={**user_headers, "Idempotency-Key": f"phase6-{suffix}"},
            json={
                "address_id": address.json()["id"],
                "items": [{"variant_id": variant.json()["id"], "quantity": 1}],
                "payment_method": "test_success",
            },
        )
        order.raise_for_status()
        order_id = order.json()["id"]

        def order_is_confirmed() -> bool:
            response = client.get(f"{base_url}:8007/api/v1/orders/{order_id}", headers=user_headers)
            response.raise_for_status()
            return response.json()["status"] == "CONFIRMED"

        _wait_for(order_is_confirmed)
        object_store = boto3.client(
            "s3",
            endpoint_url=os.environ.get("E2E_S3_ENDPOINT", f"{base_url}:9000"),
            aws_access_key_id=os.environ.get("E2E_S3_ACCESS_KEY", "minio-local"),
            aws_secret_access_key=os.environ.get("E2E_S3_SECRET_KEY", "minio-local-only"),
            region_name="us-east-1",
        )

        def invoice_and_email_are_ready() -> bool:
            try:
                object_store.head_object(
                    Bucket="fastapi-platform-invoices", Key=f"invoices/{order_id}/invoice.pdf"
                )
            except Exception:
                return False
            return (
                len(client.get(f"{base_url}:8025/api/v1/messages").json()["messages"])
                > previous_messages
            )

        _wait_for(invoice_and_email_are_ready)
