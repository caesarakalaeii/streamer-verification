"""Tests for security service."""

import pytest

from src.services.security_service import security_service


def test_generate_oauth_token_default_length():
    """Test OAuth token generation with default length."""
    token = security_service.generate_oauth_token()
    assert isinstance(token, str)
    assert len(token) == 64  # 32 bytes = 64 hex characters


def test_generate_oauth_token_custom_length():
    """Test OAuth token generation with custom length."""
    token = security_service.generate_oauth_token(length_bytes=16)
    assert isinstance(token, str)
    assert len(token) == 32  # 16 bytes = 32 hex characters


def test_generate_oauth_token_uniqueness():
    """Test that generated tokens are unique."""
    tokens = [security_service.generate_oauth_token() for _ in range(100)]
    assert len(tokens) == len(set(tokens))  # All tokens should be unique


def test_generate_verification_code_default():
    """Test verification code generation with default length."""
    code = security_service.generate_verification_code()
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()


def test_generate_verification_code_custom_length():
    """Test verification code generation with custom length."""
    code = security_service.generate_verification_code(length=8)
    assert isinstance(code, str)
    assert len(code) == 8
    assert code.isdigit()
