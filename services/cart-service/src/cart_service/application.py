from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from cart_service.cache import RedisCartCache
from cart_service.models import Cart, CartItem
from cart_service.schemas import (
    CartConsumeRequest,
    CartItemCreate,
    CartItemResponse,
    CartItemUpdate,
    CartResponse,
)


async def get_or_create_locked_cart(db: AsyncSession, customer_id: UUID) -> Cart:
    await db.execute(
        insert(Cart)
        .values(customer_id=customer_id)
        .on_conflict_do_nothing(index_elements=[Cart.customer_id])
    )
    cart = await db.scalar(select(Cart).where(Cart.customer_id == customer_id).with_for_update())
    if cart is None:
        raise RuntimeError("cart was not created")
    return cart


async def cart_response(db: AsyncSession, cart: Cart) -> CartResponse:
    items = await db.scalars(
        select(CartItem)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.created_at, CartItem.id)
    )
    return CartResponse(
        id=cart.id,
        customer_id=cart.customer_id,
        status=cart.status,
        version=cart.version,
        items=[CartItemResponse.model_validate(item) for item in items],
        created_at=cart.created_at,
        updated_at=cart.updated_at,
    )


async def get_cart(db: AsyncSession, customer_id: UUID, cache: RedisCartCache) -> CartResponse:
    cached = await cache.get(customer_id)
    if cached is not None:
        return cached
    cart = await get_or_create_locked_cart(db, customer_id)
    response = await cart_response(db, cart)
    await db.commit()
    await cache.set(response)
    return response


async def add_item(
    db: AsyncSession, customer_id: UUID, payload: CartItemCreate, cache: RedisCartCache
) -> CartResponse:
    cart = await get_or_create_locked_cart(db, customer_id)
    item = await db.scalar(
        select(CartItem)
        .where(CartItem.cart_id == cart.id, CartItem.variant_id == payload.variant_id)
        .with_for_update()
    )
    if item is None:
        db.add(CartItem(cart_id=cart.id, **payload.model_dump()))
    else:
        item.quantity = min(item.quantity + payload.quantity, 100)
    cart.version += 1
    await db.commit()
    await db.refresh(cart)
    response = await cart_response(db, cart)
    await cache.invalidate(customer_id)
    return response


async def update_item(
    db: AsyncSession,
    customer_id: UUID,
    variant_id: UUID,
    payload: CartItemUpdate,
    cache: RedisCartCache,
) -> CartResponse:
    cart = await get_or_create_locked_cart(db, customer_id)
    item = await db.scalar(
        select(CartItem)
        .where(CartItem.cart_id == cart.id, CartItem.variant_id == variant_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cart item not found")
    item.quantity = payload.quantity
    cart.version += 1
    await db.commit()
    await db.refresh(cart)
    response = await cart_response(db, cart)
    await cache.invalidate(customer_id)
    return response


async def delete_item(
    db: AsyncSession, customer_id: UUID, variant_id: UUID, cache: RedisCartCache
) -> CartResponse:
    cart = await get_or_create_locked_cart(db, customer_id)
    item = await db.scalar(
        select(CartItem)
        .where(CartItem.cart_id == cart.id, CartItem.variant_id == variant_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cart item not found")
    await db.delete(item)
    cart.version += 1
    await db.commit()
    await db.refresh(cart)
    response = await cart_response(db, cart)
    await cache.invalidate(customer_id)
    return response


async def clear_cart(db: AsyncSession, customer_id: UUID, cache: RedisCartCache) -> CartResponse:
    cart = await get_or_create_locked_cart(db, customer_id)
    items = await db.scalars(select(CartItem).where(CartItem.cart_id == cart.id).with_for_update())
    for item in items:
        await db.delete(item)
    cart.version += 1
    await db.commit()
    await db.refresh(cart)
    response = await cart_response(db, cart)
    await cache.invalidate(customer_id)
    return response


async def consume_cart_items(
    db: AsyncSession,
    customer_id: UUID,
    payload: CartConsumeRequest,
    cache: RedisCartCache,
) -> CartResponse:
    """Remove an accepted checkout selection without deleting concurrent cart changes."""
    cart = await get_or_create_locked_cart(db, customer_id)
    if cart.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cart changed during checkout"
        )

    requested = {item.variant_id: item.quantity for item in payload.items}
    items = await db.scalars(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.variant_id.in_(requested))
    )
    existing = {item.variant_id: item for item in items}
    if set(existing) != set(requested) or any(
        existing[variant_id].quantity < quantity for variant_id, quantity in requested.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cart changed during checkout"
        )

    for variant_id, quantity in requested.items():
        item = existing[variant_id]
        if item.quantity == quantity:
            await db.delete(item)
        else:
            item.quantity -= quantity
    cart.version += 1
    await db.commit()
    await db.refresh(cart)
    response = await cart_response(db, cart)
    await cache.invalidate(customer_id)
    return response
