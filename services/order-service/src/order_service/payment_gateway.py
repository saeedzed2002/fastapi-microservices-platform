from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import httpx


class PaymentGatewayUnavailable(RuntimeError):
    pass


class PaymentNotReady(RuntimeError):
    pass


class PaymentProviderRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class PaymentRedirect:
    redirect_url: str
    expires_at: datetime


def parse_payment_redirect(payload: object) -> PaymentRedirect:
    if not isinstance(payload, dict):
        raise PaymentGatewayUnavailable
    redirect_url = payload.get("redirect_url")
    expires_at = payload.get("expires_at")
    if not isinstance(redirect_url, str) or not redirect_url.startswith("https://"):
        raise PaymentGatewayUnavailable
    if not isinstance(expires_at, str):
        raise PaymentGatewayUnavailable
    try:
        return PaymentRedirect(
            redirect_url=redirect_url,
            expires_at=datetime.fromisoformat(expires_at),
        )
    except ValueError as exc:
        raise PaymentGatewayUnavailable from exc


async def start_zarinpal_checkout(
    *, base_url: str, timeout_seconds: float, order_id: UUID, access_token: str
) -> PaymentRedirect:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/v1/payments/orders/{order_id}/zarinpal",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise PaymentGatewayUnavailable from exc
    if response.status_code == 409:
        raise PaymentNotReady
    if response.status_code == 502:
        raise PaymentProviderRejected
    if response.status_code != 200:
        raise PaymentGatewayUnavailable
    try:
        return parse_payment_redirect(response.json())
    except ValueError as exc:
        raise PaymentGatewayUnavailable from exc
