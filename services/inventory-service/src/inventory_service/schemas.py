from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    initial_quantity: int = Field(default=0, ge=0, le=1_000_000_000)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()


class StockAdjustmentCreate(BaseModel):
    quantity_delta: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("quantity_delta")
    @classmethod
    def reject_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_delta must not be zero")
        return value


class StockItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    on_hand: int
    reserved: int
    available: int
    version: int
    created_at: datetime
    updated_at: datetime


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stock_item_id: UUID
    kind: str
    quantity_delta: int
    reserved_delta: int
    reason: str
    idempotency_key: str | None
    created_at: datetime


class StockAdjustmentResponse(BaseModel):
    stock_item: StockItemResponse
    movement: StockMovementResponse
