import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from search_service.main import app as search_app

from cart_service.main import app as cart_app
from catalog_service.main import app as catalog_app
from chat_service.main import app as chat_app
from customer_service.main import app as customer_app
from identity_service.main import app as identity_app
from inventory_service.main import app as inventory_app
from media_service.main import app as media_app
from notification_service.main import app as notification_app
from order_service.main import app as order_app
from payment_service.main import app as payment_app
from reference_service.main import app as reference_app
from shipping_service.main import app as shipping_app

_SERVICE_APPS: tuple[tuple[str, FastAPI], ...] = (
    ("reference-service", reference_app),
    ("identity-service", identity_app),
    ("customer-service", customer_app),
    ("catalog-service", catalog_app),
    ("search-service", search_app),
    ("media-service", media_app),
    ("inventory-service", inventory_app),
    ("cart-service", cart_app),
    ("order-service", order_app),
    ("payment-service", payment_app),
    ("shipping-service", shipping_app),
    ("notification-service", notification_app),
    ("chat-service", chat_app),
)


@pytest.mark.parametrize(("service_name", "app"), _SERVICE_APPS)
def test_service_missing_routes_use_the_canonical_error_contract(
    service_name: str, app: FastAPI
) -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/api/v1/contract-test-route-that-does-not-exist",
                headers={"x-request-id": f"{service_name}-missing-route"},
            )

    response = asyncio.run(request())
    schema_path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "openapi"
        / "error-response.v1.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))

    assert response.status_code == 404
    assert response.headers["x-request-id"] == f"{service_name}-missing-route"
    assert response.json()["error"] == {
        "code": "RESOURCE_NOT_FOUND",
        "message": "The requested resource was not found.",
        "details": {},
        "request_id": f"{service_name}-missing-route",
    }
    assert not list(validator.iter_errors(response.json()))
