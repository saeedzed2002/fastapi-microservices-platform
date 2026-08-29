from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CartItemCreate(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=100)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=100)


class CartConsumeItem(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=100)


class CartConsumeRequest(BaseModel):
    expected_version: int = Field(ge=1)
    items: list[CartConsumeItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_duplicate_variants(self) -> CartConsumeRequest:
        if len({item.variant_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate variant")
        return self


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    quantity: int
    created_at: datetime
    updated_at: datetime


class CartResponse(BaseModel):
    id: UUID
    customer_id: UUID
    status: str
    version: int
    items: list[CartItemResponse]
    created_at: datetime
    updated_at: datetime
