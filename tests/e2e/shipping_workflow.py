"""Portable Shipping-to-Order projection workflow for Compose and Kind."""

import os
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import httpx

from platform_auth import encode_access_token

try:  # The Kind runner copies these portable modules directly into /app.
    from tests.e2e.checkout_workflow import (
        AUDIENCE,
        ISSUER,
        LOCAL_SECRET,
        CheckoutWorkflowResult,
        _service_base_url,
    )
except ModuleNotFoundError:  # pragma: no cover - executed by the Kind image only.
    from checkout_workflow import (  # type: ignore[no-redef]
        AUDIENCE,
        ISSUER,
        LOCAL_SECRET,
        CheckoutWorkflowResult,
        _service_base_url,
    )


def _token(*, subject: UUID, roles: tuple[str, ...]) -> str:
    return encode_access_token(
        subject=subject,
        roles=roles,
        secret=os.environ.get("E2E_JWT_SECRET", LOCAL_SECRET),
        issuer=ISSUER,
        audience=AUDIENCE,
        ttl_seconds=900,
    )


def _wait_for(predicate: Callable[[], bool], *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for Shipping workflow state")


def run_shipping_workflow(checkout: CheckoutWorkflowResult) -> None:
    """Transition a Shipping-owned shipment and wait for Order's Kafka projection."""
    shipping_base_url = _service_base_url("shipping")
    order_base_url = _service_base_url("order")
    timeout_seconds = float(os.environ.get("E2E_WAIT_TIMEOUT_SECONDS", "45"))
    user_headers = {
        "Authorization": f"Bearer {_token(subject=checkout.customer_id, roles=('customer',))}"
    }
    administrator_headers = {
        "Authorization": f"Bearer {_token(subject=checkout.administrator_id, roles=('admin',))}"
    }

    with httpx.Client(timeout=10.0, verify=False) as client:

        def commit_processing_transition() -> bool:
            response = client.put(
                f"{shipping_base_url}/api/v1/shipping/admin/orders/{checkout.order_id}/status",
                headers={**administrator_headers, "Idempotency-Key": "phase18-processing"},
                json={"status": "PROCESSING"},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            body = response.json()
            assert body["order_id"] == str(checkout.order_id)
            assert body["status"] == "PROCESSING"
            return True

        _wait_for(commit_processing_transition, timeout_seconds=timeout_seconds)

        replay = client.put(
            f"{shipping_base_url}/api/v1/shipping/admin/orders/{checkout.order_id}/status",
            headers={**administrator_headers, "Idempotency-Key": "phase18-processing"},
            json={"status": "PROCESSING"},
        )
        replay.raise_for_status()
        assert replay.json()["status"] == "PROCESSING"

        shipped = client.put(
            f"{shipping_base_url}/api/v1/shipping/admin/orders/{checkout.order_id}/status",
            headers={**administrator_headers, "Idempotency-Key": f"phase18-shipped-{uuid4().hex}"},
            json={"status": "SHIPPED", "carrier": "Post", "tracking_number": "PHASE18-1"},
        )
        shipped.raise_for_status()
        assert shipped.json()["status"] == "SHIPPED"

        def order_projection_is_shipped() -> bool:
            response = client.get(
                f"{order_base_url}/api/v1/orders/{checkout.order_id}", headers=user_headers
            )
            response.raise_for_status()
            payload = response.json()
            return (
                payload["status"] == "SHIPPED"
                and payload["fulfillment"] is not None
                and payload["fulfillment"]["status"] == "SHIPPED"
                and payload["fulfillment"]["carrier"] == "Post"
                and payload["fulfillment"]["tracking_number"] == "PHASE18-1"
            )

        _wait_for(order_projection_is_shipped, timeout_seconds=timeout_seconds)

    print(f"shipping E2E succeeded for order {checkout.order_id}")
