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
