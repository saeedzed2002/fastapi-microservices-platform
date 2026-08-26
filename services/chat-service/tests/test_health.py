import asyncio

import httpx

from chat_service.main import app


def test_liveness() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/live")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_include_chat_operational_signals() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/metrics")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert "chat_message_acknowledgements_total" in response.text
    assert "chat_redis_fanout_publish_failures_total" in response.text
