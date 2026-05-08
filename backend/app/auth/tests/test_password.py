"""
Unit tests for app.auth.utils.password
───────────────────────────────────────
Covers:
  • hash_password  – returns bcrypt hash, never stores plain text
  • verify_password – correct / wrong / empty / whitespace variants
  • hash determinism – same input → different hashes (bcrypt salting)
"""

import pytest

from app.auth.utils.password import hash_password, verify_password


# ════════════════════════════════════════════════════════════════════════════
# hash_password
# ════════════════════════════════════════════════════════════════════════════

class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("securepassword1")
        assert isinstance(result, str)

    def test_hash_is_not_plain_password(self):
        plain = "securepassword1"
        assert hash_password(plain) != plain

    def test_hash_starts_with_bcrypt_prefix(self):
        # bcrypt hashes start with $2b$ (or $2a$)
        result = hash_password("anypassword")
        assert result.startswith("$2")

    def test_same_password_produces_different_hashes(self):
        # bcrypt uses a random salt per call
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_hash_has_sufficient_length(self):
        # A bcrypt hash is always 60 characters
        result = hash_password("password123")
        assert len(result) == 60


# ════════════════════════════════════════════════════════════════════════════
# verify_password
# ════════════════════════════════════════════════════════════════════════════

class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        plain = "correcthorsebatterystaple"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_password_against_non_empty_hash_returns_false(self):
        hashed = hash_password("nonempty")
        assert verify_password("", hashed) is False

    def test_case_sensitivity_wrong_case_returns_false(self):
        hashed = hash_password("Password123")
        assert verify_password("password123", hashed) is False

    def test_leading_whitespace_does_not_match(self):
        hashed = hash_password("password")
        assert verify_password(" password", hashed) is False

    def test_trailing_whitespace_does_not_match(self):
        hashed = hash_password("password")
        assert verify_password("password ", hashed) is False

    def test_password_with_special_chars_round_trips(self):
        plain = "P@$$w0rd!#%^&*()"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_very_long_password_round_trips(self):
        # bcrypt truncates at 72 bytes, but the API should still work
        plain = "a" * 100
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_unicode_password_round_trips(self):
        plain = "pa$$w0rd🚀✨"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True