import asyncio
from datetime import UTC, datetime
from importlib.metadata import requires
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx

import media_service.main as media_main
from media_service.application import public_product_image_download_url, request_asset_deletion
from media_service.catalog import HttpCatalogMediaGateway
from media_service.config import get_settings
from media_service.db import get_session
from media_service.models import MediaAsset, MediaDerivative, MediaTaskIntent
from platform_auth import encode_access_token


async def _session_override() -> object:
    yield object()


def test_runtime_manifest_declares_catalog_gateway_http_client() -> None:
    declared_requirements = requires("media-service") or []

    assert any(requirement.startswith("httpx") for requirement in declared_requirements)


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


def _administrator_headers() -> dict[str, str]:
    settings = get_settings()
    token = encode_access_token(
        subject=uuid4(),
        roles=("admin",),
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_seconds=300,
    )
    return {"Authorization": f"Bearer {token}"}


def test_customer_cannot_authorize_a_product_image_upload() -> None:
    async def exercise() -> None:
        media_main.app.dependency_overrides[get_session] = _session_override
        try:
            transport = httpx.ASGITransport(app=media_main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/media/uploads",
                    headers=_customer_headers(),
                    json={
                        "purpose": "product_image",
                        "content_type": "image/png",
                        "size_bytes": 1,
                        "checksum_sha256": "a" * 64,
                    },
                )
                assert response.status_code == 403
        finally:
            media_main.app.dependency_overrides.clear()

    asyncio.run(exercise())


def test_public_product_image_redirect_uses_only_a_ready_product_thumbnail() -> None:
    async def exercise() -> None:
        asset = MediaAsset(
            id=uuid4(),
            owner_subject_id=uuid4(),
            purpose="product_image",
            original_object_key="uploads/product/original",
            content_type="image/png",
            size_bytes=1,
            checksum_sha256="a" * 64,
            status="ready",
            created_at=datetime.now(UTC),
        )
        derivative = MediaDerivative(
            media_asset_id=asset.id,
            kind="thumbnail",
            object_key="uploads/product/thumbnail.webp",
            content_type="image/webp",
            size_bytes=1,
        )
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[asset, derivative]))
        storage = SimpleNamespace(
            create_download_url=lambda **_: "https://object-store.example/image.webp"
        )

        result = await public_product_image_download_url(
            session,  # type: ignore[arg-type]
            asset_id=asset.id,
            storage=storage,
            settings=get_settings(),
        )

        assert result == "https://object-store.example/image.webp"

    asyncio.run(exercise())


def test_asset_deletion_creates_one_durable_task_intent() -> None:
    async def exercise() -> None:
        asset = MediaAsset(
            id=uuid4(),
            owner_subject_id=uuid4(),
            purpose="avatar",
            original_object_key="uploads/avatar/original",
            content_type="image/png",
            size_bytes=1,
            checksum_sha256="a" * 64,
            status="ready",
            created_at=datetime.now(UTC),
        )
        added: list[object] = []
        session = SimpleNamespace(add=added.append, commit=AsyncMock())

        await request_asset_deletion(session, asset=asset)  # type: ignore[arg-type]

        assert asset.status == "deletion_pending"
        intent = next(item for item in added if isinstance(item, MediaTaskIntent))
        assert intent.task_name == "media.delete_asset.v1"
        session.commit.assert_awaited_once()

    asyncio.run(exercise())


def test_media_catalog_gateway_reads_a_boolean_reference_status() -> None:
    async def exercise() -> None:
        gateway = HttpCatalogMediaGateway(
            get_settings().model_copy(
                update={
                    "catalog_access_secret": "test-catalog-media-access-secret-at-least-32-bytes"
                }
            )
        )
        gateway._client.get = AsyncMock(return_value=httpx.Response(200, json={"referenced": True}))  # type: ignore[method-assign]

        assert await gateway.is_product_image_referenced(asset_id=uuid4()) is True
        await gateway.close()

    asyncio.run(exercise())


def test_product_image_deletion_requires_admin_and_prior_catalog_detachment() -> None:
    async def exercise() -> None:
        asset = MediaAsset(
            id=uuid4(),
            owner_subject_id=uuid4(),
            purpose="product_image",
            original_object_key="uploads/product/original",
            content_type="image/png",
            size_bytes=1,
            checksum_sha256="a" * 64,
            status="ready",
            created_at=datetime.now(UTC),
        )
        load_asset = AsyncMock(return_value=asset)
        delete_request = AsyncMock()
        reference_check = AsyncMock(return_value=True)
        media_main.app.dependency_overrides[get_session] = _session_override
        try:
            transport = httpx.ASGITransport(app=media_main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                with (
                    patch.object(media_main, "load_owned_asset_or_404", load_asset),
                    patch.object(media_main, "request_asset_deletion", delete_request),
                    patch.object(
                        media_main.catalog_gateway,
                        "is_product_image_referenced",
                        reference_check,
                    ),
                ):
                    customer = await client.delete(
                        f"/api/v1/media/assets/{asset.id}", headers=_customer_headers()
                    )
                    administrator = await client.delete(
                        f"/api/v1/media/assets/{asset.id}",
                        headers=_administrator_headers(),
                    )

            assert customer.status_code == 403
            assert administrator.status_code == 409
            delete_request.assert_not_awaited()
            reference_check.assert_awaited_once_with(asset_id=asset.id)
        finally:
            media_main.app.dependency_overrides.clear()

    asyncio.run(exercise())
