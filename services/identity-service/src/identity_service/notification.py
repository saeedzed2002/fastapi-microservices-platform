from uuid import UUID

import httpx

from identity_service.config import Settings


class NotificationUnavailable(Exception):
    pass


class NotificationOtpGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.otp_notification_base_url.rstrip("/"),
            timeout=settings.otp_notification_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def enqueue(self, *, delivery_id: UUID, phone: str) -> None:
        if self._settings.internal_otp_shared_secret is None:
            raise NotificationUnavailable
        try:
            response = await self._client.post(
                "/internal/v1/otp-deliveries",
                headers={"X-Platform-Internal-Token": self._settings.internal_otp_shared_secret},
                json={"delivery_id": str(delivery_id), "phone": phone},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationUnavailable from exc
