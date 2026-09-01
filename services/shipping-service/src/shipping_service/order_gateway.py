import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from shipping_service.config import Settings
from shipping_service.order_access import build_order_authorization_proof
from shipping_service.schemas import OrderAuthorizationResponse


class OrderAuthorizationUnavailable(Exception):
    """Order did not provide a definitive authorization result."""


class HttpOrderAuthorizationGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.order_base_url,
            timeout=settings.order_access_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def authorize(
        self,
        *,
        order_id: UUID,
        command_id: UUID,
        target_status: str,
        access_token: str,
    ) -> OrderAuthorizationResponse:
        proof_expires_at = int(time.time()) + self._settings.order_access_proof_ttl_seconds
        authorization_expires_at = datetime.fromtimestamp(proof_expires_at, UTC)
        proof = build_order_authorization_proof(
            secret=self._settings.order_internal_access_secret,
            order_id=order_id,
            command_id=command_id,
            target_status=target_status,
            expires_at=proof_expires_at,
        )
        try:
            response = await self._client.post(
                f"/api/internal/v1/orders/{order_id}/fulfillment-authorizations",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Shipping-Order-Proof": proof,
                },
                json={
                    "command_id": str(command_id),
                    "target_status": target_status,
                    "expires_at": authorization_expires_at.isoformat().replace("+00:00", "Z"),
                    "proof_expires_at": proof_expires_at,
                },
            )
        except httpx.HTTPError as exc:
            raise OrderAuthorizationUnavailable from exc
        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise OrderAuthorizationUnavailable
        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="order did not authorize shipment transition",
            )
        try:
            return OrderAuthorizationResponse.model_validate(response.json())
        except (TypeError, ValueError) as exc:
            raise OrderAuthorizationUnavailable from exc
