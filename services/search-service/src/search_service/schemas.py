from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CatalogProductProjection(BaseModel):
    product_id: UUID
    slug: str = Field(min_length=1, max_length=260)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(max_length=20_000)
    status: str = Field(pattern=r"^(draft|published)$")
    brand_id: UUID | None = None
    category_id: UUID | None = None
    price_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    attributes: dict[str, str] = Field(default_factory=dict)
    published_at: datetime | None = None
    updated_at: datetime

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class CatalogProductDeletion(BaseModel):
    product_id: UUID
    deleted_at: datetime


class SearchProductResponse(BaseModel):
    product_id: UUID
    slug: str
    name: str
    description: str
    brand_id: UUID | None
    category_id: UUID | None
    price_amount: Decimal
    currency: str
    attributes: dict[str, str]
    published_at: datetime


class SearchProductsResponse(BaseModel):
    items: list[SearchProductResponse]
    next_cursor: str | None
