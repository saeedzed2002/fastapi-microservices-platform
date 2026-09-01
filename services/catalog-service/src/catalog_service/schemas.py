from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=140)
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=140)
    parent_id: UUID | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    parent_id: UUID | None
    created_at: datetime


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=140)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=140)


class BrandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime


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
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=260)
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


class VariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    attributes: dict[str, str] | None = None
    is_active: bool | None = None


class ProductMediaAttach(BaseModel):
    media_asset_id: UUID
    sort_order: int = Field(default=0, ge=0, le=1000)


class ProductMediaUpdate(BaseModel):
    sort_order: int = Field(ge=0, le=1000)


class ProductMediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    media_asset_id: UUID
    sort_order: int
    created_at: datetime


class ProductReviewCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5_000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("review body must not be blank")
        return normalized


class ProductReviewModeration(BaseModel):
    status: Literal["approved", "rejected"]
    moderation_note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("moderation_note")
    @classmethod
    def normalize_moderation_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("moderation note must not be blank")
        return normalized


class ProductReviewReplyResponse(BaseModel):
    id: UUID
    parent_id: UUID
    body: str
    author_label: str
    created_at: datetime
    updated_at: datetime


class ProductReviewResponse(BaseModel):
    id: UUID
    body: str
    author_label: str
    created_at: datetime
    updated_at: datetime
    replies: list[ProductReviewReplyResponse]


class ProductReviewListResponse(BaseModel):
    items: list[ProductReviewResponse]
    next_cursor: str | None


class ProductReviewSubmissionResponse(BaseModel):
    id: UUID
    product_id: UUID
    parent_id: UUID | None
    status: Literal["pending", "approved"]
    created_at: datetime


class AdminProductReviewResponse(BaseModel):
    id: UUID
    product_id: UUID
    parent_id: UUID | None
    author_id: UUID
    author_role: Literal["customer", "admin"]
    body: str
    status: Literal["pending", "approved", "rejected"]
    moderated_by: UUID | None
    moderation_note: str | None
    moderated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminProductReviewListResponse(BaseModel):
    items: list[AdminProductReviewResponse]
    next_cursor: str | None


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    price_amount: Decimal | None
    attributes: dict[str, str]
    is_active: bool


class CheckoutVariantRequest(BaseModel):
    variant_ids: list[UUID] = Field(min_length=1, max_length=100)


class CheckoutVariantResponse(BaseModel):
    variant_id: UUID
    sku: str
    product_name: str
    unit_amount: Decimal
    currency: str
    attributes: dict[str, str]


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
    media_urls: list[str]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None
