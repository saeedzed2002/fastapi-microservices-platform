import hashlib
import hmac
import time
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from media_service.config import Settings


def _build_media_reference_proof(*, secret: str, asset_id: UUID, expires_at: int) -> str:
    canonical = "\n".join(("media-reference-status.v1", str(asset_id), str(expires_at)))
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


class HttpCatalogMediaGateway:
    """Read the Catalog-owned product-media reference state before asset deletion."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.catalog_base_url,
            timeout=settings.catalog_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def is_product_image_referenced(self, *, asset_id: UUID) -> bool:
        expires_at = int(time.time()) + self._settings.catalog_access_proof_max_ttl_seconds
        proof = _build_media_reference_proof(
            secret=self._settings.catalog_access_secret,
            asset_id=asset_id,
            expires_at=expires_at,
        )
        try:
            response = await self._client.get(
                f"/api/internal/v1/catalog/media-assets/{asset_id}/reference-status",
                headers={"X-Media-Access-Proof": proof},
                params={"expires_at": expires_at},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="catalog service unavailable",
            ) from exc
        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="catalog service unavailable",
            )
        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="catalog service returned an invalid response",
            )
        try:
            referenced = response.json()["referenced"]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="catalog service returned an invalid response",
            ) from exc
        if not isinstance(referenced, bool):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="catalog service returned an invalid response",
            )
        return referenced
