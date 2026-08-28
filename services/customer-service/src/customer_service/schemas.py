from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ProfileUpsert(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    avatar_media_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).lower() if value is not None else None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    display_name: str
    phone: str | None
    avatar_media_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AddressCreate(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    recipient_name: str = Field(min_length=1, max_length=120)
    line1: str = Field(min_length=1, max_length=240)
    line2: str | None = Field(default=None, max_length=240)
    city: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=32)
    country_code: str = Field(min_length=2, max_length=2)
    is_default: bool = False

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.upper()


class AddressUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=64)
    recipient_name: str | None = Field(default=None, min_length=1, max_length=120)
    line1: str | None = Field(default=None, min_length=1, max_length=240)
    line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, min_length=1, max_length=32)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    is_default: bool | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class AddressResponse(AddressCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime
