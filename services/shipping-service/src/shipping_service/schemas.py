from uuid import UUID

from pydantic import BaseModel


class OrderConfirmedPayload(BaseModel):
    order_id: UUID
