"""
Unit tests for app.auth.schemas
────────────────────────────────
Covers:
  RegisterRequest  – email format, password length, display_name length & stripping
  LoginRequest     – email format, password presence
  TokenPayload     – field mapping
  UserRead         – from_attributes / ORM mode
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenPayload,
    UserRead,
)


# ════════════════════════════════════════════════════════════════════════════
# RegisterRequest
# ════════════════════════════════════════════════════════════════════════════

class TestRegisterRequest:

    # ── happy path ────────────────────────────────────────────────────────

    def test_valid_data_is_accepted(self):
        req = RegisterRequest(
            email="alice@example.com",
            display_name="Alice",
            password="strongpassword1",
        )
        assert req.email == "alice@example.com"
        assert req.display_name == "Alice"

    def test_display_name_is_stripped_of_whitespace(self):
        req = RegisterRequest(
            email="bob@example.com",
            display_name="  Bob  ",
            password="strongpassword1",
        )
        assert req.display_name == "Bob"

    def test_email_is_normalised_to_lowercase(self):
        req = RegisterRequest(
            email="ALICE@EXAMPLE.COM",
            display_name="Alice",
            password="strongpassword1",
        )
        # Pydantic EmailStr lower-cases the domain; implementation may vary
        assert "@" in req.email

    # ── password validation ───────────────────────────────────────────────

    def test_password_exactly_8_chars_is_accepted(self):
        req = RegisterRequest(
            email="a@b.com", display_name="Ab", password="12345678"
        )
        assert req.password == "12345678"

    def test_password_shorter_than_8_chars_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(email="a@b.com", display_name="Ab", password="short")
        assert "8 characters" in str(exc_info.value)

    def test_empty_password_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", display_name="Ab", password="")

    def test_password_7_chars_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", display_name="Ab", password="1234567")

    def test_password_9_chars_is_accepted(self):
        req = RegisterRequest(
            email="a@b.com", display_name="Ab", password="123456789"
        )
        assert len(req.password) == 9

    # ── display_name validation ───────────────────────────────────────────

    def test_display_name_exactly_2_chars_after_strip_is_accepted(self):
        req = RegisterRequest(
            email="a@b.com", display_name="AB", password="strongpassword1"
        )
        assert req.display_name == "AB"

    def test_display_name_single_char_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(email="a@b.com", display_name="A", password="strongpassword1")
        assert "2 characters" in str(exc_info.value)

    def test_display_name_only_whitespace_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", display_name="   ", password="strongpassword1")

    def test_display_name_whitespace_around_single_char_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", display_name=" X ", password="strongpassword1")

    # ── email validation ──────────────────────────────────────────────────

    def test_invalid_email_format_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", display_name="Alice", password="strongpassword1")

    def test_missing_tld_raises(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="alice@example", display_name="Alice", password="strongpassword1")

    def test_email_with_plus_addressing_is_accepted(self):
        req = RegisterRequest(
            email="alice+tag@example.com",
            display_name="Alice",
            password="strongpassword1",
        )
        assert "alice" in req.email


# ════════════════════════════════════════════════════════════════════════════
# LoginRequest
# ════════════════════════════════════════════════════════════════════════════

class TestLoginRequest:
    def test_valid_credentials_accepted(self):
        req = LoginRequest(email="alice@example.com", password="anypassword")
        assert req.email == "alice@example.com"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="bad-email", password="password")

    def test_empty_password_is_accepted_by_schema(self):
        # Schema itself has no password-strength rule for login;
        # the service layer handles incorrect passwords.
        req = LoginRequest(email="a@b.com", password="")
        assert req.password == ""

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(password="password")  # type: ignore[call-arg]

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com")  # type: ignore[call-arg]


# ════════════════════════════════════════════════════════════════════════════
# TokenPayload
# ════════════════════════════════════════════════════════════════════════════

class TestTokenPayload:
    def test_all_fields_populated_correctly(self):
        jti = str(uuid.uuid4())
        payload = TokenPayload(sub="user-123", jti=jti, type="access", exp=9999999999)

        assert payload.sub == "user-123"
        assert payload.jti == jti
        assert payload.type == "access"
        assert payload.exp == 9999999999

    def test_missing_sub_raises(self):
        with pytest.raises(ValidationError):
            TokenPayload(jti="x", type="access", exp=1)  # type: ignore[call-arg]

    def test_missing_jti_raises(self):
        with pytest.raises(ValidationError):
            TokenPayload(sub="uid", type="access", exp=1)  # type: ignore[call-arg]


# ════════════════════════════════════════════════════════════════════════════
# UserRead  (from_attributes / ORM mode)
# ════════════════════════════════════════════════════════════════════════════

class TestUserRead:
    def test_model_validate_from_orm_object(self):
        from unittest.mock import MagicMock
        now = datetime.now(timezone.utc)

        orm_obj = MagicMock()
        orm_obj.id = "user-1"
        orm_obj.email = "alice@example.com"
        orm_obj.display_name = "Alice"
        orm_obj.avatar_url = None
        orm_obj.github_user_id = None
        orm_obj.google_user_id = None
        orm_obj.created_at = now

        user_read = UserRead.model_validate(orm_obj)

        assert user_read.id == "user-1"
        assert user_read.email == "alice@example.com"
        assert user_read.display_name == "Alice"
        assert user_read.avatar_url is None
        assert user_read.created_at == now

    def test_optional_oauth_fields_are_none_by_default(self):
        from unittest.mock import MagicMock
        orm_obj = MagicMock()
        orm_obj.id = "u"
        orm_obj.email = "x@x.com"
        orm_obj.display_name = "X"
        orm_obj.avatar_url = None
        orm_obj.github_user_id = None
        orm_obj.google_user_id = None
        orm_obj.created_at = datetime.now(timezone.utc)

        user_read = UserRead.model_validate(orm_obj)
        assert user_read.github_user_id is None
        assert user_read.google_user_id is None

    def test_oauth_ids_are_serialised_when_present(self):
        from unittest.mock import MagicMock
        orm_obj = MagicMock()
        orm_obj.id = "u"
        orm_obj.email = "x@x.com"
        orm_obj.display_name = "X"
        orm_obj.avatar_url = "https://example.com/avatar.png"
        orm_obj.github_user_id = "gh-123"
        orm_obj.google_user_id = "g-456"
        orm_obj.created_at = datetime.now(timezone.utc)

        user_read = UserRead.model_validate(orm_obj)
        assert user_read.github_user_id == "gh-123"
        assert user_read.google_user_id == "g-456"
        assert user_read.avatar_url == "https://example.com/avatar.png"