import time
from uuid import UUID

import httpx
from fastapi import HTTPException

from order_service.config import Settings
from order_service.models import FulfillmentAuthorization
from order_service.schemas import (
    FulfillmentCommandResponse,
    FulfillmentUpdateRequest,
    ShippingCommandRecoveryResponse,
)
from order_service.shipping_access import build_order_recovery_proof


class ShippingRecoveryUnavailable(Exception):
    """Shipping did not provide a definitive durable-command result."""


class ShippingCommandUnavailable(Exception):
    """Shipping did not provide a definitive command result."""


class HttpShippingRecoveryGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.shipping_base_url,
            timeout=settings.shipping_access_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def recover(
        self, authorization: FulfillmentAuthorization
    ) -> ShippingCommandRecoveryResponse:
        proof_expires_at = int(time.time()) + self._settings.shipping_recovery_proof_ttl_seconds
        proof = build_order_recovery_proof(
            secret=self._settings.shipping_internal_access_secret,
            command_id=authorization.command_id,
            expires_at=proof_expires_at,
        )
        try:
            response = await self._client.get(
                f"/api/internal/v1/shipping/commands/{authorization.command_id}",
                params={"proof_expires_at": proof_expires_at},
                headers={"X-Order-Shipping-Proof": proof},
            )
        except httpx.HTTPError as exc:
            raise ShippingRecoveryUnavailable from exc
        if response.status_code != 200:
            raise ShippingRecoveryUnavailable
        try:
            return ShippingCommandRecoveryResponse.model_validate(response.json())
        except (TypeError, ValueError) as exc:
            raise ShippingRecoveryUnavailable from exc

    async def forward_fulfillment_command(
        self,
        *,
        order_id: UUID,
        payload: FulfillmentUpdateRequest,
        idempotency_key: str,
        access_token: str,
    ) -> FulfillmentCommandResponse:
        try:
            response = await self._client.put(
                f"/api/v1/shipping/admin/orders/{order_id}/status",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Idempotency-Key": idempotency_key,
                },
                json=payload.model_dump(mode="json", exclude_none=True),
            )
        except httpx.HTTPError as exc:
            raise ShippingCommandUnavailable from exc
        if response.status_code >= 500:
            raise ShippingCommandUnavailable
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="shipping rejected fulfillment command",
            )
        try:
            return FulfillmentCommandResponse.model_validate(response.json())
        except (TypeError, ValueError) as exc:
            raise ShippingCommandUnavailable from exc
