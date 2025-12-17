"""OAuth session management service."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import OAuthSession
from src.database.repositories import OAuthSessionRepository
from src.services.security_service import security_service
from src.shared.constants import (
    ERROR_DISCORD_OAUTH_NOT_COMPLETED,
    ERROR_TOKEN_EXPIRED,
    ERROR_TOKEN_INVALID,
)
from src.shared.exceptions import (
    DiscordOAuthNotCompletedError,
    InvalidTokenError,
    TokenExpiredError,
)

logger = logging.getLogger(__name__)


class OAuthService:
    """Service for managing OAuth sessions."""

    @staticmethod
    async def create_session(
        db_session: AsyncSession,
        discord_user_id: int,
        discord_username: str,
        discord_guild_id: int,
    ) -> tuple[str, OAuthSession]:
        """
        Create a new OAuth session.

        Returns:
            Tuple of (token, oauth_session)
        """
        token = security_service.generate_oauth_token()
        oauth_session = await OAuthSessionRepository.create(
            db_session,
            token=token,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            discord_guild_id=discord_guild_id,
        )
        return token, oauth_session

    @staticmethod
    async def validate_token(
        db_session: AsyncSession,
        token: str,
    ) -> OAuthSession:
        """
        Validate an OAuth token and return the session.

        Raises:
            InvalidTokenError: Token not found
            TokenExpiredError: Token has expired
        """
        oauth_session = await OAuthSessionRepository.get_by_token(db_session, token)

        if oauth_session is None:
            logger.warning(f"Invalid token: {token[:8]}...")
            raise InvalidTokenError(
                f"Token not found: {token[:8]}...", ERROR_TOKEN_INVALID
            )

        if oauth_session.expires_at < datetime.utcnow():
            logger.warning(
                f"Expired token: {token[:8]}..., expired at {oauth_session.expires_at}"
            )
            raise TokenExpiredError(
                f"Token expired: {token[:8]}..., expired at {oauth_session.expires_at}",
                ERROR_TOKEN_EXPIRED,
            )

        return oauth_session

    @staticmethod
    async def complete_discord_oauth(
        db_session: AsyncSession,
        token: str,
        discord_user_id: int,
    ) -> None:
        """
        Mark Discord OAuth step as completed.

        Args:
            db_session: Database session
            token: OAuth token
            discord_user_id: Discord user ID from OAuth
        """
        await OAuthSessionRepository.mark_discord_oauth_completed(
            db_session,
            token=token,
            discord_oauth_verified_id=discord_user_id,
        )
        logger.info(
            f"Discord OAuth completed for token {token[:8]}..., user {discord_user_id}"
        )

    @staticmethod
    async def complete_twitch_oauth(
        db_session: AsyncSession,
        token: str,
        twitch_user_id: str,
        twitch_username: str,
    ) -> None:
        """
        Mark Twitch OAuth step as completed.

        Args:
            db_session: Database session
            token: OAuth token
            twitch_user_id: Twitch user ID from OAuth
            twitch_username: Twitch username from OAuth
        """
        await OAuthSessionRepository.mark_twitch_oauth_completed(
            db_session,
            token=token,
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
        )
        logger.info(
            f"Twitch OAuth completed for token {token[:8]}..., user {twitch_username}"
        )

    @staticmethod
    async def validate_discord_oauth_completed(
        db_session: AsyncSession,
        token: str,
    ) -> OAuthSession:
        """
        Validate that Discord OAuth step has been completed for this token.

        Raises:
            DiscordOAuthNotCompletedError: Discord OAuth not completed
        """
        oauth_session = await OAuthService.validate_token(db_session, token)

        if not oauth_session.discord_oauth_completed:
            logger.warning(f"Discord OAuth not completed for token {token[:8]}...")
            raise DiscordOAuthNotCompletedError(
                f"Discord OAuth not completed for token {token[:8]}...",
                ERROR_DISCORD_OAUTH_NOT_COMPLETED,
            )

        return oauth_session

    @staticmethod
    async def cleanup_expired_sessions(db_session: AsyncSession) -> int:
        """Clean up expired OAuth sessions. Returns count of deleted sessions."""
        return await OAuthSessionRepository.cleanup_expired_sessions(db_session)


# Global instance
oauth_service = OAuthService()
