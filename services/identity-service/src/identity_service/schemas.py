from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from identity_service.otp import normalize_iranian_mobile, normalize_otp_code


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class OtpRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=32)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_iranian_mobile(value)


class OtpVerifyRequest(OtpRequest):
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return normalize_otp_code(value)


class OtpRequestResponse(BaseModel):
    expires_in: int


class InternalOtpDeliveryCodeResponse(BaseModel):
    phone: str
    otp_code: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class PasswordResetRequestPayload(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class PasswordResetConfirmPayload(BaseModel):
    token: str = Field(min_length=48, max_length=512)
    new_password: str = Field(min_length=12, max_length=128)


class PasswordResetRequestResponse(BaseModel):
    accepted: bool = True


class InternalPasswordResetDeliveryResponse(BaseModel):
    email: EmailStr
    token: str


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime


class SessionPage(BaseModel):
    items: list[SessionResponse]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr | None
    phone: str | None
    status: str
    roles: list[str]
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: UserResponse
