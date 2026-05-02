import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.auth.schemas import TokenPayload
from app.config import get_settings

settings = get_settings()


def _create_token(user_id: str, token_type: str, expires_delta: timedelta) -> tuple[str, str]:
    """Returns (encoded_token, jti). jti is stored in Redis for revocation."""
    jti = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": token_type,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def create_access_token(user_id: str) -> tuple[str, str]:
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> tuple[str, str]:
    return _create_token(
        user_id,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return TokenPayload(**payload)
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e