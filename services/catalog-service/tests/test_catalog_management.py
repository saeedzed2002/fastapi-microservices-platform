import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx

from catalog_service.application import delete_product, restore_product
from catalog_service.config import get_settings
from catalog_service.db import get_session
from catalog_service.main import app
from catalog_service.media import build_media_reference_proof
from catalog_service.models import Product
from platform_auth import encode_access_token


async def _session_override() -> object:
    yield object()


def _customer_headers() -> dict[str, str]:
    settings = get_settings()
    token = encode_access_token(
        subject=uuid4(),
        roles=("customer",),
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_seconds=300,
    )
    return {"Authorization": f"Bearer {token}"}


def test_customer_tokens_cannot_mutate_catalog_management_resources() -> None:
    product_id, category_id, brand_id, asset_id, variant_id = (uuid4() for _ in range(5))
    requests = (
        (
            "POST",
            "/api/v1/catalog/products",
            {"name": "Phone", "slug": "phone", "price_amount": "1.00", "currency": "IRT"},
        ),
        ("PATCH", f"/api/v1/catalog/products/{product_id}", {"name": "Changed"}),
        ("DELETE", f"/api/v1/catalog/products/{product_id}", None),
        ("POST", f"/api/v1/catalog/products/{product_id}/restore", None),
        ("POST", "/api/v1/catalog/categories", {"name": "Phones", "slug": "phones"}),
        ("PATCH", f"/api/v1/catalog/categories/{category_id}", {"name": "Changed"}),
        ("DELETE", f"/api/v1/catalog/categories/{category_id}", None),
        ("POST", "/api/v1/catalog/brands", {"name": "Acme", "slug": "acme"}),
        ("PATCH", f"/api/v1/catalog/brands/{brand_id}", {"name": "Changed"}),
        ("DELETE", f"/api/v1/catalog/brands/{brand_id}", None),
        ("POST", f"/api/v1/catalog/products/{product_id}/media", {"media_asset_id": str(asset_id)}),
        ("PATCH", f"/api/v1/catalog/products/{product_id}/media/{asset_id}", {"sort_order": 1}),
        ("DELETE", f"/api/v1/catalog/products/{product_id}/media/{asset_id}", None),
        (
            "POST",
            f"/api/v1/catalog/products/{product_id}/variants",
            {"sku": "PHONE-1", "name": "Phone"},
        ),
        (
            "PATCH",
            f"/api/v1/catalog/products/{product_id}/variants/{variant_id}",
            {"name": "Changed"},
        ),
        ("DELETE", f"/api/v1/catalog/products/{product_id}/variants/{variant_id}", None),
    )

    async def exercise() -> None:
        app.dependency_overrides[get_session] = _session_override
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                for method, path, payload in requests:
                    response = await client.request(
                        method,
                        path,
                        headers=_customer_headers(),
                        json=payload,
                    )
                    assert response.status_code == 403, (method, path, response.text)
        finally:
            app.dependency_overrides.clear()

    asyncio.run(exercise())


def test_media_reference_status_is_available_only_to_a_signed_media_request() -> None:
    async def exercise() -> None:
        asset_id = uuid4()
        settings = get_settings()
        expires_at = int(datetime.now(UTC).timestamp()) + 30
        proof = build_media_reference_proof(
            secret=settings.media_internal_access_secret,
            asset_id=asset_id,
            expires_at=expires_at,
        )
        referenced_session = SimpleNamespace(scalar=AsyncMock(return_value=asset_id))

        async def reference_session_override() -> object:
            yield referenced_session

        app.dependency_overrides[get_session] = reference_session_override
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/internal/v1/catalog/media-assets/{asset_id}/reference-status",
                    params={"expires_at": expires_at},
                    headers={"X-Media-Access-Proof": proof},
                )
                assert response.status_code == 200
                assert response.json() == {"referenced": True}
        finally:
            app.dependency_overrides.clear()

    asyncio.run(exercise())


def test_product_delete_archives_and_removes_the_public_search_projection() -> None:
    async def exercise() -> None:
        product = Product(
            id=uuid4(),
            name="Phone",
            slug="phone",
            status="published",
            price_amount="1.00",
            currency="IRT",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        added: list[object] = []
        session = SimpleNamespace(add=added.append, commit=AsyncMock())

        await delete_product(session, product)  # type: ignore[arg-type]

        assert product.status == "archived"
        assert product.archived_at is not None
        assert added[0].event_type == "product.deleted.v1"
        session.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_product_restore_returns_an_archived_product_to_an_unpublished_draft() -> None:
    async def exercise() -> None:
        product = Product(
            id=uuid4(),
            name="Phone",
            slug="phone",
            status="archived",
            price_amount="1.00",
            currency="IRT",
            published_at=datetime.now(UTC),
            archived_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session = SimpleNamespace(
            add=lambda _: None,
            flush=AsyncMock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        restored = await restore_product(session, product)  # type: ignore[arg-type]

        assert restored.status == "draft"
        assert restored.archived_at is None
        assert restored.published_at is None
        session.commit.assert_awaited_once()

    asyncio.run(exercise())
