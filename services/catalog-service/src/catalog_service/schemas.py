from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=260)
    description: str = Field(default="", max_length=20_000)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    price_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20_000)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    price_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    attributes: dict[str, str] | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class VariantCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=160)
    price_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    attributes: dict[str, str] = Field(default_factory=dict)


class ProductMediaAttach(BaseModel):
    media_asset_id: UUID
    sort_order: int = Field(default=0, ge=0, le=1000)


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    price_amount: Decimal | None
    attributes: dict[str, str]
    is_active: bool


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str
    status: str
    brand_id: UUID | None
    category_id: UUID | None
    price_amount: Decimal
    currency: str
    attributes: dict[str, str]
    media_asset_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
