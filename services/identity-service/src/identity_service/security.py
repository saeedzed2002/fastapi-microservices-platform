import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from identity_service.config import Settings

password_hasher = PasswordHasher(
    time_cost=3, memory_cost=65_536, parallelism=4, hash_len=32, salt_len=16
)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(session_id: UUID) -> str:
    return f"{session_id}.{secrets.token_urlsafe(48)}"


def parse_refresh_session_id(token: str) -> UUID:
    try:
        return UUID(token.split(".", 1)[0])
    except (IndexError, ValueError) as exc:
        raise ValueError("invalid refresh token") from exc


def refresh_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
