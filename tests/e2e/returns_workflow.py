"""Portable delivered-order return workflow for Compose and Kind."""

import os
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import httpx

try:  # The Kind runner copies these portable modules directly into /app.
    from tests.e2e.checkout_workflow import CheckoutWorkflowResult, _service_base_url
    from tests.e2e.shipping_workflow import _token, run_delivered_shipping_workflow
except ModuleNotFoundError:  # pragma: no cover - executed by the Kind image only.
    from checkout_workflow import (  # type: ignore[no-redef]
        CheckoutWorkflowResult,
        _service_base_url,
    )
    from shipping_workflow import _token, run_delivered_shipping_workflow  # type: ignore[no-redef]


def _wait_for(predicate: Callable[[], bool], *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError("timed out waiting for post-delivery return workflow state")


def run_returns_workflow(checkout: CheckoutWorkflowResult) -> None:
    """Prove receipt-gated restock and a correlated local test-payment refund."""
    run_delivered_shipping_workflow(checkout)
    order_base_url = _service_base_url("order")
    inventory_base_url = _service_base_url("inventory")
    timeout_seconds = float(os.environ.get("E2E_WAIT_TIMEOUT_SECONDS", "45"))
    user_headers = {
        "Authorization": f"Bearer {_token(subject=checkout.customer_id, roles=('customer',))}"
    }
    administrator_headers = {
        "Authorization": f"Bearer {_token(subject=checkout.administrator_id, roles=('admin',))}"
    }
    suffix = uuid4().hex

    with httpx.Client(timeout=10.0, verify=False) as client:
        requested = client.post(
            f"{order_base_url}/api/v1/orders/{checkout.order_id}/returns",
            headers={**user_headers, "Idempotency-Key": f"phase19-request-{suffix}"},
            json={"reason": "Phase 19 end-to-end return"},
        )
        requested.raise_for_status()
        return_request_id = UUID(requested.json()["id"])
        assert requested.status_code == 202
        assert requested.json()["status"] == "REQUESTED"

        replay = client.post(
            f"{order_base_url}/api/v1/orders/{checkout.order_id}/returns",
            headers={**user_headers, "Idempotency-Key": f"phase19-request-{suffix}"},
            json={"reason": "ignored on idempotent replay"},
        )
        replay.raise_for_status()
        assert replay.json()["id"] == str(return_request_id)

        listed = client.get(
            f"{order_base_url}/api/v1/orders/admin/returns", headers=administrator_headers
        )
        listed.raise_for_status()
        assert str(return_request_id) in {item["id"] for item in listed.json()["items"]}

        decision = client.post(
            f"{order_base_url}/api/v1/orders/admin/returns/{return_request_id}/decision",
            headers={**administrator_headers, "Idempotency-Key": f"phase19-decision-{suffix}"},
            json={"status": "APPROVED", "note": "received for inspection"},
        )
        decision.raise_for_status()
        assert decision.status_code == 202
        assert decision.json()["status"] == "APPROVED"

        receipt = client.post(
            f"{order_base_url}/api/v1/orders/admin/returns/{return_request_id}/receipt",
            headers={**administrator_headers, "Idempotency-Key": f"phase19-receipt-{suffix}"},
        )
        receipt.raise_for_status()
        assert receipt.status_code == 202
        assert receipt.json()["status"] == "REFUND_PENDING"

        receipt_replay = client.post(
            f"{order_base_url}/api/v1/orders/admin/returns/{return_request_id}/receipt",
            headers={**administrator_headers, "Idempotency-Key": f"phase19-receipt-{suffix}"},
        )
        receipt_replay.raise_for_status()
        assert receipt_replay.json()["id"] == str(return_request_id)

        def stock_is_restored_once() -> bool:
            response = client.get(
                f"{inventory_base_url}/api/v1/inventory/stock-items/{checkout.sku}",
                headers=administrator_headers,
            )
            response.raise_for_status()
            payload = response.json()
            return payload["on_hand"] == 2 and payload["reserved"] == 0

        _wait_for(stock_is_restored_once, timeout_seconds=timeout_seconds)

        def return_is_financially_complete() -> bool:
            response = client.get(
                f"{order_base_url}/api/v1/orders/{checkout.order_id}", headers=user_headers
            )
            response.raise_for_status()
            payload = response.json()
            return (
                payload["status"] == "REFUNDED"
                and payload["return_request"] is not None
                and payload["return_request"]["status"] == "REFUNDED"
            )

        _wait_for(return_is_financially_complete, timeout_seconds=timeout_seconds)

    print(f"returns E2E succeeded for order {checkout.order_id}")
