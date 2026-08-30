import hashlib
import hmac
import time
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from catalog_service.config import Settings


def build_catalog_access_proof(
    *, secret: str, subject_id: UUID, asset_id: UUID, expires_at: int
) -> str:
    canonical = "\n".join((str(subject_id), str(asset_id), str(expires_at)))
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


class HttpMediaCatalogGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.media_base_url,
            timeout=settings.media_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def validate_product_image(self, *, asset_id: UUID, owner_subject_id: UUID) -> None:
        expires_at = int(time.time()) + self._settings.media_access_proof_ttl_seconds
        proof = build_catalog_access_proof(
            secret=self._settings.media_internal_access_secret,
            subject_id=owner_subject_id,
            asset_id=asset_id,
            expires_at=expires_at,
        )
        try:
            response = await self._client.post(
                f"/api/internal/v1/media/catalog-assets/{asset_id}/attachment-availability",
                headers={"X-Catalog-Access-Proof": proof},
                json={
                    "owner_subject_id": str(owner_subject_id),
                    "expires_at": expires_at,
                },
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="media service unavailable",
            ) from exc
        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="media service unavailable",
            )
        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="media asset is not ready for product attachment",
            )
        try:
            returned_asset_id = UUID(str(response.json()["asset_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="media service returned an invalid response",
            ) from exc
        if returned_asset_id != asset_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="media service returned an invalid response",
            )
