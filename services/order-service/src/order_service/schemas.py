from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckoutItem(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=100)


class CheckoutRequest(BaseModel):
    address_id: UUID
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    payment_method: str = Field(pattern=r"^test_(success|failure)$")


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    sku: str
    product_name: str
    unit_amount: Decimal
    quantity: int
    attributes: dict[str, str]


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    tracking_code: str
    currency: str
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
