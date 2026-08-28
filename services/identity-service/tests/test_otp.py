import asyncio
import json
from uuid import UUID

import pytest

from identity_service.config import Settings
from identity_service.otp import (
    OtpInvalid,
    OtpStateStore,
    normalize_iranian_mobile,
    normalize_otp_code,
)
from identity_service.schemas import OtpVerifyRequest


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def aclose(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
        keepttl: bool = False,
    ) -> bool:
        del ex, keepttl
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                deleted += 1
        return deleted


@pytest.mark.parametrize(
    ("raw_phone", "normalized"),
    [
        ("09121234567", "989121234567"),
        ("+989121234567", "989121234567"),
        ("۰۰۹۸۹۱۲۱۲۳۴۵۶۷", "989121234567"),
    ],
)
def test_normalize_iranian_mobile_accepts_supported_notation(
    raw_phone: str, normalized: str
) -> None:
    assert normalize_iranian_mobile(raw_phone) == normalized


def test_normalize_iranian_mobile_rejects_non_mobile_number() -> None:
    with pytest.raises(ValueError, match="Iranian mobile"):
        normalize_iranian_mobile("02112345678")


def test_otp_code_normalizes_persian_and_arabic_digits() -> None:
    assert normalize_otp_code("۱۲۳۴۵۶") == "123456"
    assert OtpVerifyRequest(phone="09121234567", code="١٢٣٤٥٦").code == "123456"


def test_empty_internal_otp_secret_is_an_unconfigured_secret() -> None:
    assert Settings(internal_otp_shared_secret="").internal_otp_shared_secret is None


def test_otp_state_does_not_embed_raw_code_and_success_consumes_delivery() -> None:
    async def exercise() -> None:
        store = OtpStateStore(Settings())
        fake_redis = FakeRedis()
        store._client = fake_redis  # type: ignore[assignment]
        challenge = await store.create_challenge(
            phone="989121234567", delivery_id=UUID("11111111-1111-4111-8111-111111111111")
        )

        state = json.loads(fake_redis.values[store._state_key(challenge.phone)])
        assert "code" not in state
        assert (await store.get_delivery_challenge(challenge.delivery_id)).code == challenge.code

        await store.verify_challenge(phone=challenge.phone, code=challenge.code)

        with pytest.raises(OtpInvalid):
            await store.get_delivery_challenge(challenge.delivery_id)

    asyncio.run(exercise())


def test_otp_attempt_limit_consumes_pending_delivery() -> None:
    async def exercise() -> None:
        store = OtpStateStore(Settings(otp_max_verify_attempts=2))
        fake_redis = FakeRedis()
        store._client = fake_redis  # type: ignore[assignment]
        challenge = await store.create_challenge(
            phone="989121234567", delivery_id=UUID("22222222-2222-4222-8222-222222222222")
        )
        invalid_code = "000000" if challenge.code != "000000" else "999999"

        for _ in range(2):
            with pytest.raises(OtpInvalid):
                await store.verify_challenge(phone=challenge.phone, code=invalid_code)

        with pytest.raises(OtpInvalid):
            await store.get_delivery_challenge(challenge.delivery_id)

    asyncio.run(exercise())


def test_discard_removes_delivery_when_state_was_already_removed() -> None:
    async def exercise() -> None:
        store = OtpStateStore(Settings())
        fake_redis = FakeRedis()
        store._client = fake_redis  # type: ignore[assignment]
        challenge = await store.create_challenge(
            phone="989121234567", delivery_id=UUID("33333333-3333-4333-8333-333333333333")
        )
        await fake_redis.delete(store._state_key(challenge.phone))

        await store.discard_challenge(challenge)

        assert store._delivery_key(challenge.delivery_id) not in fake_redis.values

    asyncio.run(exercise())
