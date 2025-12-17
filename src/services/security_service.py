"""Security service for token generation and validation."""

import secrets

from src.config import config


class SecurityService:
    """Service for security-related operations."""

    @staticmethod
    def generate_oauth_token(length_bytes: int | None = None) -> str:
        """
        Generate a cryptographically secure random token for OAuth sessions.

        Args:
            length_bytes: Length of token in bytes. Defaults to config value.

        Returns:
            Hex-encoded random token string.
        """
        if length_bytes is None:
            length_bytes = config.oauth_token_length_bytes
        return secrets.token_hex(length_bytes)

    @staticmethod
    def generate_verification_code(length: int = 6) -> str:
        """
        Generate a random numeric verification code.

        Args:
            length: Number of digits in the code.

        Returns:
            Numeric code string.
        """
        return "".join(str(secrets.randbelow(10)) for _ in range(length))


# Global instance
security_service = SecurityService()
