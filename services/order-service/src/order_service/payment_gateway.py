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


class PaymentProviderNotConfigured(RuntimeError):
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


def _payment_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail if isinstance(detail, str) else None


async def start_zarinpal_checkout(
    *, base_url: str, timeout_seconds: float, order_id: UUID, access_token: str
) -> PaymentRedirect:
    return await _start_payment_checkout(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        order_id=order_id,
        access_token=access_token,
        method="zarinpal",
    )


async def start_online_checkout(
    *, base_url: str, timeout_seconds: float, order_id: UUID, access_token: str
) -> PaymentRedirect:
    return await _start_payment_checkout(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        order_id=order_id,
        access_token=access_token,
        method="online",
    )


async def _start_payment_checkout(
    *,
    base_url: str,
    timeout_seconds: float,
    order_id: UUID,
    access_token: str,
    method: str,
) -> PaymentRedirect:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/v1/payments/orders/{order_id}/{method}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise PaymentGatewayUnavailable from exc
    if response.status_code == 409:
        raise PaymentNotReady
    if response.status_code == 502:
        raise PaymentProviderRejected
    if response.status_code == 503:
        if _payment_error_detail(response) == "payment provider is not configured":
            raise PaymentProviderNotConfigured
        raise PaymentGatewayUnavailable
    if response.status_code != 200:
        raise PaymentGatewayUnavailable
    try:
        return parse_payment_redirect(response.json())
    except ValueError as exc:
        raise PaymentGatewayUnavailable from exc
