import asyncio

import httpx

from reference_service.main import app


def test_liveness() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/live")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_reference_propagates_request_context() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/api/v1/reference",
                headers={"x-request-id": "request-123", "x-correlation-id": "correlation-456"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["request_id"] == "request-123"
    assert response.json()["correlation_id"] == "correlation-456"
    assert response.headers["x-request-id"] == "request-123"
