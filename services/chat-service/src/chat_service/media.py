import hashlib
import hmac
import time
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from chat_service.config import Settings
from chat_service.schemas import AttachmentDownloadResponse, MediaAssetResponse, MediaAttachment


class MediaAttachmentGateway(Protocol):
    async def validate_attachments(
        self, *, asset_ids: Sequence[UUID], access_token: str
    ) -> list[MediaAttachment]: ...

    async def create_download_url(
        self,
        *,
        subject_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        attachment: MediaAttachment,
    ) -> AttachmentDownloadResponse: ...


def build_media_access_proof(
    *,
    secret: str,
    subject_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    asset_id: UUID,
    expires_at: int,
) -> str:
    canonical = "\n".join(
        (
            str(subject_id),
            str(conversation_id),
            str(message_id),
            str(asset_id),
            str(expires_at),
        )
    )
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


class HttpMediaAttachmentGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.media_base_url,
            timeout=settings.media_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def validate_attachments(
        self, *, asset_ids: Sequence[UUID], access_token: str
    ) -> list[MediaAttachment]:
        attachments: list[MediaAttachment] = []
        for asset_id in asset_ids:
            try:
                response = await self._client.get(
                    f"/api/v1/media/assets/{asset_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
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
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media attachment is not authorized",
                )
            try:
                asset = MediaAssetResponse.model_validate(response.json())
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="media service returned an invalid response",
                ) from exc
            if asset.purpose != "chat_attachment" or asset.status != "ready":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="media attachment is not ready",
                )
            attachments.append(
                MediaAttachment(
                    asset_id=asset.id,
                    content_type=asset.content_type,
                    size_bytes=asset.size_bytes,
                )
            )
        return attachments

    async def create_download_url(
        self,
        *,
        subject_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        attachment: MediaAttachment,
    ) -> AttachmentDownloadResponse:
        expires_at = int(time.time()) + 60
        proof = build_media_access_proof(
            secret=self._settings.media_internal_access_secret,
            subject_id=subject_id,
            conversation_id=conversation_id,
            message_id=message_id,
            asset_id=attachment.asset_id,
            expires_at=expires_at,
        )
        try:
            response = await self._client.post(
                f"/api/internal/v1/media/chat-attachments/{attachment.asset_id}/download-url",
                headers={"X-Chat-Access-Proof": proof},
                json={
                    "subject_id": str(subject_id),
                    "conversation_id": str(conversation_id),
                    "message_id": str(message_id),
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
                detail="media attachment is unavailable",
            )
        try:
            return AttachmentDownloadResponse.model_validate(response.json())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="media service returned an invalid response",
            ) from exc
