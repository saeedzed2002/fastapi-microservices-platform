import asyncio
import json
import secrets
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from identity_service.config import Settings
from identity_service.security import hash_password, verify_password


class OtpError(Exception):
    """Base type for non-sensitive OTP failures."""


class OtpUnavailable(OtpError):
    pass


class OtpRateLimited(OtpError):
    pass


class OtpInvalid(OtpError):
    pass


class OtpBusy(OtpError):
    pass


@dataclass(frozen=True)
class OtpChallenge:
    phone: str
    code: str
    delivery_id: UUID


_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_TRANSLATION = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, "01234567890123456789")


def normalize_iranian_mobile(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_DIGIT_TRANSLATION)
    compact = "".join(character for character in normalized if character not in " -()")
    if compact.startswith("+"):
        compact = compact[1:]
    if compact.startswith("00"):
        compact = compact[2:]
    if compact.startswith("0"):
        compact = "98" + compact[1:]
    elif compact.startswith("9") and not compact.startswith("98"):
        compact = "98" + compact
    if (
        len(compact) != 12
        or not compact.startswith("989")
        or not compact.isascii()
        or not compact.isdigit()
    ):
        raise ValueError("phone must be an Iranian mobile number")
    return compact


def normalize_otp_code(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(_DIGIT_TRANSLATION)


class OtpStateStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Redis.from_url(settings.otp_redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def create_challenge(self, *, phone: str, delivery_id: UUID) -> OtpChallenge:
        cooldown_key = self._cooldown_key(phone)
        state_key = self._state_key(phone)
        rate_key = self._rate_key(phone)
        challenge = OtpChallenge(phone=phone, code=self._generate_code(), delivery_id=delivery_id)
        code_hash = await asyncio.to_thread(hash_password, challenge.code)
        try:
            cooldown_set = await self._client.set(
                cooldown_key,
                str(delivery_id),
                ex=self._settings.otp_resend_cooldown_seconds,
                nx=True,
            )
            if not cooldown_set:
                raise OtpRateLimited
            rate_count = await self._client.incr(rate_key)
            if rate_count == 1:
                await self._client.expire(rate_key, self._settings.otp_phone_rate_window_seconds)
            if rate_count > self._settings.otp_phone_rate_limit:
                await self._delete_if_matches(cooldown_key, str(delivery_id))
                raise OtpRateLimited
            state = json.dumps(
                {
                    "delivery_id": str(delivery_id),
                    "code_hash": code_hash,
                    "attempts": 0,
                },
                separators=(",", ":"),
            )
            await self._client.set(state_key, state, ex=self._settings.otp_code_ttl_seconds)
            await self._client.set(
                self._delivery_key(delivery_id),
                json.dumps({"phone": phone, "code": challenge.code}, separators=(",", ":")),
                ex=self._settings.otp_code_ttl_seconds,
            )
        except OtpRateLimited:
            raise
        except RedisError as exc:
            await self.discard_challenge(challenge)
            raise OtpUnavailable from exc
        return challenge

    async def discard_challenge(self, challenge: OtpChallenge) -> None:
        try:
            await self._delete_if_matches(
                self._cooldown_key(challenge.phone), str(challenge.delivery_id)
            )
            raw_state = await self._client.get(self._state_key(challenge.phone))
            if raw_state is not None:
                state = json.loads(raw_state)
                if state.get("delivery_id") == str(challenge.delivery_id):
                    await self._client.delete(self._state_key(challenge.phone))
            await self._client.delete(self._delivery_key(challenge.delivery_id))
        except (RedisError, ValueError, TypeError):
            return

    async def verify_challenge(self, *, phone: str, code: str) -> None:
        lock_key = self._lock_key(phone)
        try:
            locked = await self._client.set(lock_key, "1", ex=5, nx=True)
        except RedisError as exc:
            raise OtpUnavailable from exc
        if not locked:
            raise OtpBusy
        try:
            await self._verify_locked(phone=phone, code=code)
        finally:
            with suppress(RedisError):
                await self._client.delete(lock_key)

    async def _verify_locked(self, *, phone: str, code: str) -> None:
        state_key = self._state_key(phone)
        try:
            raw_state = await self._client.get(state_key)
            if raw_state is None:
                raise OtpInvalid
            state = json.loads(raw_state)
            attempts = state.get("attempts")
            code_hash = state.get("code_hash")
            delivery_id_raw = state.get("delivery_id")
            if (
                not isinstance(attempts, int)
                or not isinstance(code_hash, str)
                or not isinstance(delivery_id_raw, str)
            ):
                await self._client.delete(state_key)
                raise OtpInvalid
            delivery_id = UUID(delivery_id_raw)
            valid = await asyncio.to_thread(verify_password, code, code_hash)
            if valid:
                await self._client.delete(state_key)
                await self._client.delete(self._delivery_key(delivery_id))
                return
            attempts += 1
            if attempts >= self._settings.otp_max_verify_attempts:
                await self._client.delete(state_key)
                await self._client.delete(self._delivery_key(delivery_id))
            else:
                state["attempts"] = attempts
                await self._client.set(
                    state_key,
                    json.dumps(state, separators=(",", ":")),
                    keepttl=True,
                )
            raise OtpInvalid
        except OtpInvalid:
            raise
        except (RedisError, ValueError, TypeError) as exc:
            raise OtpUnavailable from exc

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _state_key(phone: str) -> str:
        return f"fastapi-platform:identity:otp:v1:challenge:{phone}"

    @staticmethod
    def _cooldown_key(phone: str) -> str:
        return f"fastapi-platform:identity:otp:v1:cooldown:{phone}"

    @staticmethod
    def _rate_key(phone: str) -> str:
        return f"fastapi-platform:identity:otp:v1:request-rate:{phone}"

    @staticmethod
    def _lock_key(phone: str) -> str:
        return f"fastapi-platform:identity:otp:v1:verify-lock:{phone}"

    @staticmethod
    def _delivery_key(delivery_id: UUID) -> str:
        return f"fastapi-platform:identity:otp:v1:delivery:{delivery_id}"

    async def get_delivery_challenge(self, delivery_id: UUID) -> OtpChallenge:
        try:
            raw_delivery = await self._client.get(self._delivery_key(delivery_id))
            if raw_delivery is None:
                raise OtpInvalid
            delivery = json.loads(raw_delivery)
            phone = delivery.get("phone")
            code = delivery.get("code")
            if not isinstance(phone, str) or not isinstance(code, str):
                raise OtpInvalid
            return OtpChallenge(phone=phone, code=code, delivery_id=delivery_id)
        except OtpInvalid:
            raise
        except (RedisError, ValueError, TypeError) as exc:
            raise OtpUnavailable from exc

    async def _delete_if_matches(self, key: str, expected: str) -> None:
        current = await self._client.get(key)
        if current == expected:
            await self._client.delete(key)
