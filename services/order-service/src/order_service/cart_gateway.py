from dataclasses import dataclass
from uuid import UUID

import httpx


class CartGatewayUnavailable(RuntimeError):
    pass


class EmptyCart(RuntimeError):
    pass


@dataclass(frozen=True)
class CartCheckoutSnapshot:
    version: int
    item_quantities: dict[UUID, int]


def parse_cart_checkout_snapshot(payload: object) -> CartCheckoutSnapshot:
    if not isinstance(payload, dict):
        raise CartGatewayUnavailable
    version = payload.get("version")
    items = payload.get("items")
    if not isinstance(version, int) or version < 1 or not isinstance(items, list):
        raise CartGatewayUnavailable

    quantities: dict[UUID, int] = {}
    for item in items:
        if not isinstance(item, dict):
            raise CartGatewayUnavailable
        try:
            variant_id = UUID(str(item["variant_id"]))
            quantity = int(item["quantity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CartGatewayUnavailable from exc
        if quantity < 1 or quantity > 100 or variant_id in quantities:
            raise CartGatewayUnavailable
        quantities[variant_id] = quantity
    if not quantities:
        raise EmptyCart
    return CartCheckoutSnapshot(version=version, item_quantities=quantities)


async def fetch_cart_checkout_snapshot(
    *, base_url: str, timeout_seconds: float, access_token: str
) -> CartCheckoutSnapshot:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/api/v1/carts/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise CartGatewayUnavailable from exc
    if response.status_code != 200:
        raise CartGatewayUnavailable
    try:
        return parse_cart_checkout_snapshot(response.json())
    except ValueError as exc:
        raise CartGatewayUnavailable from exc


async def consume_cart_checkout_snapshot(
    *,
    base_url: str,
    timeout_seconds: float,
    access_token: str,
    snapshot: CartCheckoutSnapshot,
) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/v1/carts/me/consume",
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "expected_version": snapshot.version,
                    "items": [
                        {"variant_id": str(variant_id), "quantity": quantity}
                        for variant_id, quantity in snapshot.item_quantities.items()
                    ],
                },
            )
    except httpx.RequestError as exc:
        raise CartGatewayUnavailable from exc
    if response.status_code == 409:
        return False
    if response.status_code != 200:
        raise CartGatewayUnavailable
    return True
