from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class ZarinpalStartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    authority: str
    redirect_url: HttpUrl
    expires_at: datetime


class ZarinpalCallbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    payment_status: str
    provider_reference: str | None
