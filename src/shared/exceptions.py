"""Custom exceptions for the application."""


class BotException(Exception):
    """Base exception for all bot-related errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        """
        Initialize exception.

        Args:
            message: Internal error message for logging
            user_message: User-friendly error message to display
        """
        super().__init__(message)
        self.user_message = user_message or message


# OAuth Session Errors
class OAuthError(BotException):
    """Base OAuth error."""


class TokenExpiredError(OAuthError):
    """Token has expired."""


class TokenAlreadyUsedError(OAuthError):
    """Token already consumed."""


class InvalidTokenError(OAuthError):
    """Token not found."""


class DiscordOAuthNotCompletedError(OAuthError):
    """Discord OAuth step not completed."""


# Verification Errors
class VerificationError(BotException):
    """Base verification error."""


class TwitchAccountAlreadyLinkedError(VerificationError):
    """Twitch account linked to different Discord user."""


class DiscordAccountAlreadyLinkedError(VerificationError):
    """Discord account linked to different Twitch account."""


class AlreadyVerifiedError(VerificationError):
    """User already verified."""


class DiscordUserMismatchError(VerificationError):
    """Discord user ID doesn't match expected user."""


# Permission Errors
class PermissionError(BotException):
    """Bot lacks required permissions."""


class NoNicknamePermissionError(PermissionError):
    """Cannot manage nicknames."""


class NoRolePermissionError(PermissionError):
    """Cannot manage roles."""


# Database Errors
class DatabaseError(BotException):
    """Database operation failed."""


class RecordNotFoundError(DatabaseError):
    """Database record not found."""


class RecordAlreadyExistsError(DatabaseError):
    """Database record already exists."""


# API Errors
class APIError(BotException):
    """External API error."""


class DiscordAPIError(APIError):
    """Discord API error."""


class TwitchAPIError(APIError):
    """Twitch API error."""
