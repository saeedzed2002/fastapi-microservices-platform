from uuid import UUID

import httpx

from notification_service.config import Settings


class IdentityOtpUnavailable(Exception):
    pass


class IdentityOtpGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_delivery_code(self, delivery_id: UUID) -> tuple[str, str]:
        if self._settings.internal_otp_shared_secret is None:
            raise IdentityOtpUnavailable("internal OTP delivery is not configured")
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.identity_otp_base_url.rstrip("/"),
                timeout=self._settings.identity_otp_timeout_seconds,
            ) as client:
                response = await client.get(
                    f"/internal/v1/otp-deliveries/{delivery_id}/code",
                    headers={
                        "X-Platform-Internal-Token": self._settings.internal_otp_shared_secret
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IdentityOtpUnavailable("OTP delivery data is unavailable") from exc
        phone = payload.get("phone") if isinstance(payload, dict) else None
        otp_code = payload.get("otp_code") if isinstance(payload, dict) else None
        if not isinstance(phone, str) or not isinstance(otp_code, str):
            raise IdentityOtpUnavailable("OTP delivery data is invalid")
        return phone, otp_code


class IdentityPasswordResetUnavailable(Exception):
    pass


class IdentityPasswordResetGateway:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_delivery_token(self, delivery_id: UUID) -> tuple[str, str]:
        if self._settings.internal_otp_shared_secret is None:
            raise IdentityPasswordResetUnavailable(
                "internal password reset delivery is not configured"
            )
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.identity_otp_base_url.rstrip("/"),
                timeout=self._settings.identity_otp_timeout_seconds,
            ) as client:
                response = await client.get(
                    f"/internal/v1/password-reset-deliveries/{delivery_id}",
                    headers={
                        "X-Platform-Internal-Token": self._settings.internal_otp_shared_secret
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IdentityPasswordResetUnavailable(
                "password reset delivery data is unavailable"
            ) from exc
        email = payload.get("email") if isinstance(payload, dict) else None
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(email, str) or not isinstance(token, str):
            raise IdentityPasswordResetUnavailable("password reset delivery data is invalid")
        return email, token
