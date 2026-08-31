from uuid import UUID

from pydantic import BaseModel, Field


class OtpSmsDeliveryRequest(BaseModel):
    delivery_id: UUID
    phone: str = Field(pattern=r"^989\d{9}$")


class OtpSmsDeliveryResponse(BaseModel):
    delivery_id: UUID


class PasswordResetEmailDeliveryRequest(BaseModel):
    delivery_id: UUID
    email: str = Field(min_length=3, max_length=320)


class PasswordResetEmailDeliveryResponse(BaseModel):
    delivery_id: UUID
