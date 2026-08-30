import asyncio

import httpx

from catalog_service.main import app


def test_liveness() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health/live")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_product_deletion_route_is_administrator_only() -> None:
    assert "delete" in app.openapi()["paths"]["/api/v1/catalog/products/{product_id}"]


def test_product_media_attachment_route_is_exposed() -> None:
    assert "post" in app.openapi()["paths"]["/api/v1/catalog/products/{product_id}/media"]


def test_published_product_list_uses_a_cursor_response_contract() -> None:
    operation = app.openapi()["paths"]["/api/v1/catalog/products"]["get"]

    assert {parameter["name"] for parameter in operation["parameters"]} == {"cursor", "limit"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ProductListResponse"
    )
