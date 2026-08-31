import asyncio

import httpx

from payment_service.main import app


def test_liveness() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/live")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_zarinpal_routes_are_present_in_payment_openapi() -> None:
    openapi = app.openapi()

    start = openapi["paths"]["/api/v1/payments/orders/{order_id}/zarinpal"]["post"]
    callback = openapi["paths"]["/api/v1/payments/zarinpal/callback"]["get"]

    assert start["responses"]["200"]["description"] == "Successful Response"
    assert set(start["responses"]) == {"200", "401", "403", "409", "422", "502", "503"}
    assert start["security"] == [{"HTTPBearer": []}]
    assert set(callback["responses"]) == {"200", "404", "409", "422", "502", "503"}
    assert callback["parameters"] == [
        {
            "name": "Authority",
            "in": "query",
            "required": True,
            "schema": {"type": "string", "minLength": 1, "maxLength": 64, "title": "Authority"},
        },
        {
            "name": "Status",
            "in": "query",
            "required": True,
            "schema": {"type": "string", "minLength": 1, "maxLength": 32, "title": "Status"},
        },
    ]
    assert "/api/v1/payments/orders/{order_id}/zarinpal/reverse" not in openapi["paths"]


def test_online_payment_and_zibal_callback_routes_are_present_in_payment_openapi() -> None:
    openapi = app.openapi()

    start = openapi["paths"]["/api/v1/payments/orders/{order_id}/online"]["post"]
    callback = openapi["paths"]["/api/v1/payments/zibal/callback"]["get"]

    assert start["responses"]["200"]["description"] == "Successful Response"
    assert callback["parameters"][0]["name"] == "trackId"
