from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckoutItem(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=100)


class CheckoutRequest(BaseModel):
    address_id: UUID
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    payment_method: Literal["test_success", "test_failure", "zarinpal", "online"]


class CartCheckoutRequest(BaseModel):
    address_id: UUID


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: UUID
    sku: str
    product_name: str
    unit_amount: Decimal
    quantity: int
    attributes: dict[str, str]


class FulfillmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    carrier: str | None
    tracking_number: str | None
    updated_at: datetime


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
    fulfillment: FulfillmentResponse | None


class CartCheckoutResponse(BaseModel):
    order: OrderResponse
    redirect_url: str
    expires_at: datetime


OrderStatus = Literal[
    "PENDING",
    "INVENTORY_RESERVED",
    "PAYMENT_PENDING",
    "CONFIRMED",
    "PROCESSING",
    "SHIPPED",
    "DELIVERED",
    "REFUND_PENDING",
    "REFUNDED",
    "CANCELLED",
]
FulfillmentStatus = Literal["PROCESSING", "SHIPPED", "DELIVERED"]


class FulfillmentUpdateRequest(BaseModel):
    status: FulfillmentStatus
    carrier: str | None = Field(default=None, min_length=1, max_length=120)
    tracking_number: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_tracking_for_shipment(self) -> FulfillmentUpdateRequest:
        if self.status == "SHIPPED" and (self.carrier is None or self.tracking_number is None):
            raise ValueError("carrier and tracking_number are required when shipping an order")
        return self


class FulfillmentCommandResponse(BaseModel):
    order_id: UUID
    status: FulfillmentStatus
    carrier: str | None
    tracking_number: str | None
    command_id: UUID
    occurred_at: datetime


class RefundRequestResponse(BaseModel):
    order_id: UUID
    refund_request_id: UUID
    status: Literal["REFUND_PENDING"]


class FulfillmentAuthorizationRequest(BaseModel):
    command_id: UUID
    target_status: FulfillmentStatus
    expires_at: datetime
    proof_expires_at: int = Field(ge=1)


class FulfillmentAuthorizationResponse(BaseModel):
    authorization_id: UUID
    order_id: UUID
    command_id: UUID
    target_status: FulfillmentStatus
    expires_at: datetime


class ShippingStatusUpdatedPayload(BaseModel):
    order_id: UUID
    authorization_id: UUID
    command_id: UUID
    requested_by: UUID
    status: FulfillmentStatus
    carrier: str | None
    tracking_number: str | None
    occurred_at: datetime


class ShippingCommandRecoveryResponse(BaseModel):
    command_id: UUID
    state: Literal["NOT_COMMITTED", "COMMITTED"]
    order_id: UUID | None = None
    authorization_id: UUID | None = None
    event_id: UUID | None = None
    requested_by: UUID | None = None
    status: FulfillmentStatus | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    occurred_at: datetime | None = None


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
    refund_request_id: UUID | None


class AdminOrderPage(BaseModel):
    items: list[OrderSummaryResponse]
    next_cursor: str | None
