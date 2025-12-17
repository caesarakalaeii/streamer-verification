"""Core verification service with 1-to-1 mapping enforcement."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories import (
    UserVerificationRepository,
    VerificationAuditLogRepository,
)
from src.shared.constants import (
    AUDIT_ACTION_VERIFY_FAILED,
    AUDIT_ACTION_VERIFY_SUCCESS,
    ERROR_DISCORD_ALREADY_LINKED,
    ERROR_TWITCH_ALREADY_LINKED,
)
from src.shared.exceptions import (
    DiscordAccountAlreadyLinkedError,
    TwitchAccountAlreadyLinkedError,
)

logger = logging.getLogger(__name__)


class VerificationService:
    """Service for managing user verifications with 1-to-1 mapping enforcement."""

    @staticmethod
    async def verify_user(
        db_session: AsyncSession,
        discord_user_id: int,
        discord_username: str,
        twitch_user_id: str,
        twitch_username: str,
        twitch_display_name: str | None = None,
    ) -> None:
        """
        Verify a user by linking their Discord and Twitch accounts.

        Enforces 1-to-1 mapping:
        - 1 Discord user can only be linked to 1 Twitch account
        - 1 Twitch account can only be linked to 1 Discord user

        Args:
            db_session: Database session
            discord_user_id: Discord user ID
            discord_username: Discord username (for audit)
            twitch_user_id: Twitch user ID
            twitch_username: Twitch username
            twitch_display_name: Twitch display name (optional)

        Raises:
            DiscordAccountAlreadyLinkedError: Discord account already linked to different Twitch
            TwitchAccountAlreadyLinkedError: Twitch account already linked to different Discord
        """
        # Check if Discord user is already linked to a different Twitch account
        existing_discord = await UserVerificationRepository.get_by_discord_id(db_session, discord_user_id)
        if existing_discord and existing_discord.twitch_user_id != twitch_user_id:
            logger.warning(
                f"Discord user {discord_user_id} already linked to Twitch {existing_discord.twitch_user_id}, "
                f"cannot link to {twitch_user_id}"
            )
            await VerificationAuditLogRepository.create(
                db_session,
                discord_user_id=discord_user_id,
                discord_username=discord_username,
                twitch_user_id=twitch_user_id,
                twitch_username=twitch_username,
                action=AUDIT_ACTION_VERIFY_FAILED,
                reason="discord_user_different_twitch",
            )
            raise DiscordAccountAlreadyLinkedError(
                f"Discord user {discord_user_id} already linked to different Twitch account",
                ERROR_DISCORD_ALREADY_LINKED,
            )

        # Check if Twitch account is already linked to a different Discord user
        existing_twitch = await UserVerificationRepository.get_by_twitch_id(db_session, twitch_user_id)
        if existing_twitch and existing_twitch.discord_user_id != discord_user_id:
            logger.warning(
                f"Twitch user {twitch_user_id} already linked to Discord {existing_twitch.discord_user_id}, "
                f"cannot link to {discord_user_id}"
            )
            await VerificationAuditLogRepository.create(
                db_session,
                discord_user_id=discord_user_id,
                discord_username=discord_username,
                twitch_user_id=twitch_user_id,
                twitch_username=twitch_username,
                action=AUDIT_ACTION_VERIFY_FAILED,
                reason="twitch_account_already_linked",
            )
            raise TwitchAccountAlreadyLinkedError(
                f"Twitch user {twitch_user_id} already linked to different Discord user",
                ERROR_TWITCH_ALREADY_LINKED,
            )

        # Create or update verification record
        verification = await UserVerificationRepository.upsert(
            db_session,
            discord_user_id=discord_user_id,
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
            twitch_display_name=twitch_display_name,
        )

        # Create audit log entry
        await VerificationAuditLogRepository.create(
            db_session,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
            action=AUDIT_ACTION_VERIFY_SUCCESS,
        )

        logger.info(f"✅ Verified Discord user {discord_user_id} → Twitch user {twitch_username}")

    @staticmethod
    async def unverify_user(
        db_session: AsyncSession,
        discord_user_id: int,
        admin_username: str | None = None,
    ) -> bool:
        """
        Unverify a user by removing their Discord-Twitch link.

        Args:
            db_session: Database session
            discord_user_id: Discord user ID
            admin_username: Username of admin performing action (for audit)

        Returns:
            True if user was unverified, False if not found
        """
        # Get existing verification for audit log
        existing = await UserVerificationRepository.get_by_discord_id(db_session, discord_user_id)

        # Delete verification
        deleted = await UserVerificationRepository.delete_by_discord_id(db_session, discord_user_id)

        if deleted and existing:
            # Create audit log entry
            await VerificationAuditLogRepository.create(
                db_session,
                discord_user_id=discord_user_id,
                twitch_user_id=existing.twitch_user_id,
                twitch_username=existing.twitch_username,
                action="unverify",
                reason=f"unverified_by_admin_{admin_username}" if admin_username else "unverified",
            )
            logger.info(f"Unverified Discord user {discord_user_id}")

        return deleted

    @staticmethod
    async def get_verification_by_discord_id(db_session: AsyncSession, discord_user_id: int):
        """Get verification by Discord user ID."""
        return await UserVerificationRepository.get_by_discord_id(db_session, discord_user_id)

    @staticmethod
    async def get_all_verifications(db_session: AsyncSession):
        """Get all verifications."""
        return await UserVerificationRepository.get_all(db_session)


# Global instance
verification_service = VerificationService()
