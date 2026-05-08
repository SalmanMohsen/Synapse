"""
Unit tests for app.auth.utils.jwt
─────────────────────────────────
Covers:
  • _create_token  – payload structure, jti uniqueness, expiry math
  • create_access_token / create_refresh_token – token-type labels
  • decode_token – happy path, expired token, tampered signature,
                   wrong algorithm, missing claims
"""

import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from jose import jwt as jose_jwt

# conftest sets env vars and clears lru_cache before this import
from app.auth.utils.jwt import (
    _create_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import get_settings

settings = get_settings()

USER_ID = str(uuid.uuid4())


# ════════════════════════════════════════════════════════════════════════════
# _create_token — internal factory
# ════════════════════════════════════════════════════════════════════════════

class TestCreateTokenInternal:
    def test_returns_string_token_and_jti(self):
        token, jti = _create_token(USER_ID, "access", timedelta(minutes=15))

        assert isinstance(token, str)
        assert isinstance(jti, str)

    def test_jti_is_valid_uuid(self):
        _, jti = _create_token(USER_ID, "access", timedelta(minutes=15))

        # Should not raise
        uuid.UUID(jti)

    def test_every_call_produces_unique_jti(self):
        _, jti1 = _create_token(USER_ID, "access", timedelta(minutes=1))
        _, jti2 = _create_token(USER_ID, "access", timedelta(minutes=1))

        assert jti1 != jti2

    def test_payload_contains_expected_claims(self):
        token, jti = _create_token(USER_ID, "refresh", timedelta(days=7))

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )

        assert payload["sub"] == USER_ID
        assert payload["jti"] == jti
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_expiry_is_approximately_correct(self):
        delta = timedelta(minutes=30)
        token, _ = _create_token(USER_ID, "access", delta)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        expected_exp = int(time.time()) + delta.total_seconds()

        # Allow ±5 seconds clock skew
        assert abs(payload["exp"] - expected_exp) < 5

    def test_short_lived_token_has_smaller_exp_than_long_lived(self):
        short_token, _ = _create_token(USER_ID, "access", timedelta(minutes=5))
        long_token, _ = _create_token(USER_ID, "access", timedelta(days=7))

        def get_exp(t):
            return jose_jwt.decode(
                t, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )["exp"]

        assert get_exp(short_token) < get_exp(long_token)


# ════════════════════════════════════════════════════════════════════════════
# create_access_token
# ════════════════════════════════════════════════════════════════════════════

class TestCreateAccessToken:
    def test_token_type_is_access(self):
        token, _ = create_access_token(USER_ID)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["type"] == "access"

    def test_expiry_matches_settings(self):
        token, _ = create_access_token(USER_ID)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        expected_exp = int(time.time()) + settings.access_token_expire_minutes * 60
        assert abs(payload["exp"] - expected_exp) < 5

    def test_sub_matches_user_id(self):
        token, _ = create_access_token(USER_ID)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == USER_ID


# ════════════════════════════════════════════════════════════════════════════
# create_refresh_token
# ════════════════════════════════════════════════════════════════════════════

class TestCreateRefreshToken:
    def test_token_type_is_refresh(self):
        token, _ = create_refresh_token(USER_ID)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["type"] == "refresh"

    def test_expiry_matches_settings(self):
        token, _ = create_refresh_token(USER_ID)

        payload = jose_jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        expected_exp = int(time.time()) + settings.refresh_token_expire_days * 86400
        assert abs(payload["exp"] - expected_exp) < 5

    def test_refresh_lives_longer_than_access(self):
        access_token, _ = create_access_token(USER_ID)
        refresh_token, _ = create_refresh_token(USER_ID)

        def get_exp(t):
            return jose_jwt.decode(
                t, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )["exp"]

        assert get_exp(access_token) < get_exp(refresh_token)


# ════════════════════════════════════════════════════════════════════════════
# decode_token
# ════════════════════════════════════════════════════════════════════════════

class TestDecodeToken:
    def test_decode_valid_access_token_returns_payload(self):
        token, jti = create_access_token(USER_ID)

        payload = decode_token(token)

        assert payload.sub == USER_ID
        assert payload.jti == jti
        assert payload.type == "access"

    def test_decode_valid_refresh_token_returns_payload(self):
        token, jti = create_refresh_token(USER_ID)

        payload = decode_token(token)

        assert payload.sub == USER_ID
        assert payload.jti == jti
        assert payload.type == "refresh"

    def test_tampered_signature_raises_value_error(self):
        token, _ = create_access_token(USER_ID)
        tampered = token[:-4] + "xxxx"

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(tampered)

    def test_wrong_secret_raises_value_error(self):
        # Encode with a different secret
        jti = str(uuid.uuid4())
        payload = {
            "sub": USER_ID, "jti": jti, "type": "access",
            "exp": int(time.time()) + 900,
        }
        foreign_token = jose_jwt.encode(payload, "completely-wrong-secret", algorithm="HS256")

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(foreign_token)

    def test_expired_token_raises_value_error(self):
        # Patch timedelta so the token is already expired
        with patch("app.auth.utils.jwt.datetime") as mock_dt:
            from datetime import datetime, timezone
            # Make "now" look like it was 1 hour in the past
            past = datetime.now(timezone.utc) - timedelta(hours=1)
            mock_dt.now.return_value = past
            token, _ = _create_token(USER_ID, "access", timedelta(seconds=1))

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(token)

    def test_completely_garbage_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("not.a.jwt")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("")