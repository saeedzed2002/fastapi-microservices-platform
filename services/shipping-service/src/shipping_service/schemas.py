from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderConfirmedPayload(BaseModel):
    order_id: UUID


ShipmentStatus = Literal["PROCESSING", "SHIPPED", "DELIVERED"]


class ShipmentStatusUpdateRequest(BaseModel):
    status: ShipmentStatus
    carrier: str | None = Field(default=None, min_length=1, max_length=120)
    tracking_number: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_tracking_for_shipment(self) -> ShipmentStatusUpdateRequest:
        if self.status == "SHIPPED" and (self.carrier is None or self.tracking_number is None):
            raise ValueError("carrier and tracking_number are required when shipping an order")
        return self


class ShipmentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    status: ShipmentStatus
    carrier: str | None
    tracking_number: str | None
    command_id: UUID
    occurred_at: datetime


class OrderAuthorizationRequest(BaseModel):
    command_id: UUID
    target_status: ShipmentStatus
    expires_at: datetime


class OrderAuthorizationResponse(BaseModel):
    authorization_id: UUID
    order_id: UUID
    command_id: UUID
    target_status: ShipmentStatus
    expires_at: datetime


class ShippingStatusUpdatedPayload(BaseModel):
    order_id: UUID
    authorization_id: UUID
    command_id: UUID
    requested_by: UUID
    status: ShipmentStatus
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
    status: ShipmentStatus | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    occurred_at: datetime | None = None
