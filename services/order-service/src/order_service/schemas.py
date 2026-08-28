from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckoutItem(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=100)


class CheckoutRequest(BaseModel):
    address_id: UUID
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    payment_method: Literal["test_success", "test_failure", "zarinpal"]


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


OrderStatus = Literal["PENDING", "INVENTORY_RESERVED", "PAYMENT_PENDING", "CONFIRMED", "CANCELLED"]


class OrderSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: OrderStatus
    tracking_code: str
    currency: str
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime


class CustomerOrderPage(BaseModel):
    items: list[OrderSummaryResponse]
    next_cursor: str | None


class OrderStateTransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: OrderStatus | None
    to_status: OrderStatus
    reason: str
    created_at: datetime


class InvoiceSummaryResponse(BaseModel):
    status: str
    generated_at: datetime | None


class AdminOrderResponse(OrderResponse):
    customer_id: UUID
    customer_email: str | None
    delivery_address: dict[str, str]
    payment_method: str
    transitions: list[OrderStateTransitionResponse]
    invoice: InvoiceSummaryResponse | None


class AdminOrderPage(BaseModel):
    items: list[OrderSummaryResponse]
    next_cursor: str | None
