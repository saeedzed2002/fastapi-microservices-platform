from uuid import UUID

import httpx


class OrderGatewayUnavailable(RuntimeError):
    pass


class OrderNotPayable(RuntimeError):
    pass


async def ensure_customer_can_pay_order(
    *,
    base_url: str,
    timeout_seconds: float,
    order_id: UUID,
    access_token: str,
) -> None:
    """Ask Order to enforce ownership; Payment never reads the Order database."""
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/api/v1/orders/{order_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise OrderGatewayUnavailable from exc
    if response.status_code in {401, 403, 404}:
        raise OrderNotPayable
    if response.status_code >= 500:
        raise OrderGatewayUnavailable
    if response.status_code != 200:
        raise OrderNotPayable
    try:
        payload = response.json()
    except ValueError as exc:
        raise OrderGatewayUnavailable from exc
    if not isinstance(payload, dict) or payload.get("status") != "PAYMENT_PENDING":
        raise OrderNotPayable
