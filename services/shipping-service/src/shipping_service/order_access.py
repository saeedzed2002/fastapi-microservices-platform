import hashlib
import hmac
import time
from uuid import UUID

from fastapi import HTTPException, status

from shipping_service.config import Settings


def build_order_authorization_proof(
    *, secret: str, order_id: UUID, command_id: UUID, target_status: str, expires_at: int
) -> str:
    canonical = "\n".join(
        (
            "shipping.order.authorization.v1",
            str(order_id),
            str(command_id),
            target_status,
            str(expires_at),
        )
    )
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_order_recovery_proof(
    *, settings: Settings, provided_proof: str, command_id: UUID, expires_at: int
) -> None:
    now = int(time.time())
    if expires_at <= now or expires_at > now + settings.order_access_proof_ttl_seconds:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid order access proof"
        )
    canonical = "\n".join(("order.shipping.recovery.v1", str(command_id), str(expires_at)))
    secrets = [settings.order_internal_access_secret]
    if settings.order_internal_access_previous_secret is not None:
        secrets.append(settings.order_internal_access_previous_secret)
    for secret in secrets:
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, provided_proof):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid order access proof")
