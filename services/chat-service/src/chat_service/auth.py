from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chat_service.config import Settings, get_settings
from platform_auth import AuthClaims, TokenError, decode_access_token

bearer = HTTPBearer(auto_error=False)


def decode_chat_access_token(token: str, settings: Settings) -> AuthClaims:
    return decode_access_token(
        token,
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthClaims:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        return decode_chat_access_token(credentials.credentials, get_settings())
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token"
        ) from exc
