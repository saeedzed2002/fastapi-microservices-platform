import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from catalog_service.config import Settings
from catalog_service.media import HttpMediaCatalogGateway


def test_catalog_media_gateway_accepts_a_matching_ready_asset() -> None:
    async def exercise() -> None:
        asset_id = uuid4()
        gateway = HttpMediaCatalogGateway(
            Settings(
                media_internal_access_secret="test-catalog-media-access-secret-at-least-32-bytes"
            )
        )
        gateway._client.post = AsyncMock(  # type: ignore[method-assign]
            return_value=httpx.Response(200, json={"asset_id": str(asset_id)})
        )

        await gateway.validate_product_image(asset_id=asset_id, owner_subject_id=uuid4())
        await gateway.close()

    asyncio.run(exercise())


def test_catalog_media_gateway_rejects_an_unready_asset() -> None:
    async def exercise() -> None:
        gateway = HttpMediaCatalogGateway(
            Settings(
                media_internal_access_secret="test-catalog-media-access-secret-at-least-32-bytes"
            )
        )
        gateway._client.post = AsyncMock(return_value=httpx.Response(409))  # type: ignore[method-assign]

        with pytest.raises(HTTPException) as exc_info:
            await gateway.validate_product_image(asset_id=uuid4(), owner_subject_id=uuid4())
        assert exc_info.value.status_code == 409
        await gateway.close()

    asyncio.run(exercise())
