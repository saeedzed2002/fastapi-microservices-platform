from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inventory_service.models import StockItem, StockMovement
from inventory_service.schemas import (
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    StockItemCreate,
    StockItemResponse,
    StockMovementResponse,
)


def stock_item_response(stock_item: StockItem) -> StockItemResponse:
    return StockItemResponse(
        id=stock_item.id,
        sku=stock_item.sku,
        on_hand=stock_item.on_hand,
        reserved=stock_item.reserved,
        available=stock_item.on_hand - stock_item.reserved,
        version=stock_item.version,
        created_at=stock_item.created_at,
        updated_at=stock_item.updated_at,
    )


async def load_stock_item_or_404(db: AsyncSession, sku: str) -> StockItem:
    stock_item = await db.scalar(select(StockItem).where(StockItem.sku == sku.upper()))
    if stock_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stock item not found")
    return stock_item


async def create_stock_item(db: AsyncSession, payload: StockItemCreate) -> StockItem:
    stock_item = StockItem(sku=payload.sku, on_hand=payload.initial_quantity)
    db.add(stock_item)
    try:
        await db.flush()
        db.add(
            StockMovement(
                stock_item_id=stock_item.id,
                kind="initial",
                quantity_delta=payload.initial_quantity,
                reason="initial stock",
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="stock item SKU exists"
        ) from exc
    await db.refresh(stock_item)
    return stock_item


async def adjust_stock(
    db: AsyncSession, sku: str, payload: StockAdjustmentCreate
) -> StockAdjustmentResponse:
    stock_item = await db.scalar(
        select(StockItem).where(StockItem.sku == sku.upper()).with_for_update()
    )
    if stock_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stock item not found")

    existing = await db.scalar(
        select(StockMovement).where(StockMovement.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        if (
            existing.stock_item_id != stock_item.id
            or existing.quantity_delta != payload.quantity_delta
            or existing.reason != payload.reason
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotency key was used with a different adjustment",
            )
        return StockAdjustmentResponse(
            stock_item=stock_item_response(stock_item),
            movement=StockMovementResponse.model_validate(existing),
        )

    next_on_hand = stock_item.on_hand + payload.quantity_delta
    if next_on_hand < stock_item.reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="adjustment would reduce on-hand stock below reserved stock",
        )

    stock_item.on_hand = next_on_hand
    stock_item.version += 1
    movement = StockMovement(
        stock_item_id=stock_item.id,
        kind="adjustment",
        quantity_delta=payload.quantity_delta,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
    )
    db.add(movement)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="duplicate stock adjustment"
        ) from exc
    await db.refresh(stock_item)
    await db.refresh(movement)
    return StockAdjustmentResponse(
        stock_item=stock_item_response(stock_item),
        movement=StockMovementResponse.model_validate(movement),
    )


async def list_stock_movements(
    db: AsyncSession, stock_item_id: UUID
) -> list[StockMovementResponse]:
    movements = await db.scalars(
        select(StockMovement)
        .where(StockMovement.stock_item_id == stock_item_id)
        .order_by(StockMovement.created_at, StockMovement.id)
    )
    return [StockMovementResponse.model_validate(movement) for movement in movements]
