"""Data access layer (repositories) for database operations."""

import logging
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import config
from src.database.models import (
    GuildConfig,
    OAuthSession,
    UserVerification,
    VerificationAuditLog,
)
from src.shared.exceptions import RecordAlreadyExistsError

logger = logging.getLogger(__name__)


class UserVerificationRepository:
    """Repository for UserVerification table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        discord_user_id: int,
        twitch_user_id: str,
        twitch_username: str,
        twitch_display_name: str | None = None,
    ) -> UserVerification:
        """Create a new user verification record."""
        verification = UserVerification(
            discord_user_id=discord_user_id,
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
            twitch_display_name=twitch_display_name,
            verified_at=datetime.utcnow(),
        )
        session.add(verification)
        try:
            await session.flush()
            logger.info(
                f"Created verification for Discord user {discord_user_id} → Twitch user {twitch_username}"
            )
            return verification
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating verification: {e}")
            raise RecordAlreadyExistsError(
                "User verification already exists",
                "This Discord or Twitch account is already linked.",
            ) from e

    @staticmethod
    async def get_by_discord_id(
        session: AsyncSession, discord_user_id: int
    ) -> UserVerification | None:
        """Get verification by Discord user ID."""
        result = await session.execute(
            select(UserVerification).where(
                UserVerification.discord_user_id == discord_user_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_twitch_id(
        session: AsyncSession, twitch_user_id: str
    ) -> UserVerification | None:
        """Get verification by Twitch user ID."""
        result = await session.execute(
            select(UserVerification).where(
                UserVerification.twitch_user_id == twitch_user_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(session: AsyncSession) -> Sequence[UserVerification]:
        """Get all user verifications."""
        result = await session.execute(select(UserVerification))
        return result.scalars().all()

    @staticmethod
    async def update_nickname_check(
        session: AsyncSession, verification_id: int
    ) -> None:
        """Update last nickname check timestamp."""
        await session.execute(
            update(UserVerification)
            .where(UserVerification.id == verification_id)
            .values(last_nickname_check=datetime.utcnow())
        )
        await session.flush()

    @staticmethod
    async def update_nickname_update(
        session: AsyncSession, verification_id: int
    ) -> None:
        """Update last nickname update timestamp."""
        await session.execute(
            update(UserVerification)
            .where(UserVerification.id == verification_id)
            .values(
                last_nickname_update=datetime.utcnow(),
                last_nickname_check=datetime.utcnow(),
            )
        )
        await session.flush()

    @staticmethod
    async def delete_by_discord_id(session: AsyncSession, discord_user_id: int) -> bool:
        """Delete verification by Discord user ID. Returns True if deleted, False if not found."""
        result = await session.execute(
            delete(UserVerification).where(
                UserVerification.discord_user_id == discord_user_id
            )
        )
        await session.flush()
        deleted: bool = result.rowcount > 0  # type: ignore[attr-defined]
        if deleted:
            logger.info(f"Deleted verification for Discord user {discord_user_id}")
        return deleted

    @staticmethod
    async def upsert(
        session: AsyncSession,
        discord_user_id: int,
        twitch_user_id: str,
        twitch_username: str,
        twitch_display_name: str | None = None,
    ) -> UserVerification:
        """Create or update verification. Returns the verification record."""
        existing = await UserVerificationRepository.get_by_discord_id(
            session, discord_user_id
        )
        if existing:
            # Update existing
            existing.twitch_user_id = twitch_user_id
            existing.twitch_username = twitch_username
            existing.twitch_display_name = twitch_display_name
            existing.verified_at = datetime.utcnow()
            await session.flush()
            logger.info(f"Updated verification for Discord user {discord_user_id}")
            return existing
        else:
            # Create new
            return await UserVerificationRepository.create(
                session,
                discord_user_id,
                twitch_user_id,
                twitch_username,
                twitch_display_name,
            )


class OAuthSessionRepository:
    """Repository for OAuthSession table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        token: str,
        discord_user_id: int,
        discord_username: str,
        discord_guild_id: int,
    ) -> OAuthSession:
        """Create a new OAuth session."""
        expires_at = datetime.utcnow() + timedelta(
            minutes=config.oauth_token_expiry_minutes
        )
        oauth_session = OAuthSession(
            token=token,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            discord_guild_id=discord_guild_id,
            expires_at=expires_at,
        )
        session.add(oauth_session)
        await session.flush()
        logger.info(
            f"Created OAuth session for Discord user {discord_user_id}, token={token[:8]}..."
        )
        return oauth_session

    @staticmethod
    async def get_by_token(session: AsyncSession, token: str) -> OAuthSession | None:
        """Get OAuth session by token."""
        result = await session.execute(
            select(OAuthSession).where(OAuthSession.token == token)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_discord_oauth_completed(
        session: AsyncSession,
        token: str,
        discord_oauth_verified_id: int,
    ) -> None:
        """Mark Discord OAuth as completed."""
        await session.execute(
            update(OAuthSession)
            .where(OAuthSession.token == token)
            .values(
                discord_oauth_completed=True,
                discord_oauth_verified_id=discord_oauth_verified_id,
                discord_oauth_completed_at=datetime.utcnow(),
            )
        )
        await session.flush()
        logger.info(f"Marked Discord OAuth completed for token {token[:8]}...")

    @staticmethod
    async def mark_twitch_oauth_completed(
        session: AsyncSession,
        token: str,
        twitch_user_id: str,
        twitch_username: str,
    ) -> None:
        """Mark Twitch OAuth as completed."""
        await session.execute(
            update(OAuthSession)
            .where(OAuthSession.token == token)
            .values(
                twitch_oauth_completed=True,
                twitch_user_id=twitch_user_id,
                twitch_username=twitch_username,
                twitch_oauth_completed_at=datetime.utcnow(),
            )
        )
        await session.flush()
        logger.info(f"Marked Twitch OAuth completed for token {token[:8]}...")

    @staticmethod
    async def cleanup_expired_sessions(session: AsyncSession) -> int:
        """Delete expired OAuth sessions that haven't completed. Returns count of deleted sessions."""
        result = await session.execute(
            delete(OAuthSession).where(
                OAuthSession.expires_at < datetime.utcnow(),
                ~OAuthSession.twitch_oauth_completed,
            )
        )
        await session.flush()
        deleted_count: int = result.rowcount  # type: ignore[attr-defined]
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired OAuth sessions")
        return deleted_count


class VerificationAuditLogRepository:
    """Repository for VerificationAuditLog table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        discord_user_id: int,
        action: str,
        discord_username: str | None = None,
        discord_guild_id: int | None = None,
        twitch_user_id: str | None = None,
        twitch_username: str | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VerificationAuditLog | None:
        """Create an audit log entry."""
        if not config.enable_audit_logging:
            logger.debug("Audit logging disabled, skipping log entry")
            return None

        log_entry = VerificationAuditLog(
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            discord_guild_id=discord_guild_id,
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
            action=action,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(log_entry)
        await session.flush()
        logger.debug(f"Created audit log: {action} for Discord user {discord_user_id}")
        return log_entry

    @staticmethod
    async def get_by_discord_user(
        session: AsyncSession,
        discord_user_id: int,
        limit: int = 100,
    ) -> Sequence[VerificationAuditLog]:
        """Get audit logs for a Discord user."""
        result = await session.execute(
            select(VerificationAuditLog)
            .where(VerificationAuditLog.discord_user_id == discord_user_id)
            .order_by(VerificationAuditLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_by_action(
        session: AsyncSession,
        action: str,
        limit: int = 100,
    ) -> Sequence[VerificationAuditLog]:
        """Get audit logs by action type."""
        result = await session.execute(
            select(VerificationAuditLog)
            .where(VerificationAuditLog.action == action)
            .order_by(VerificationAuditLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class GuildConfigRepository:
    """Repository for GuildConfig table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        guild_id: int,
        guild_name: str,
        verified_role_id: int,
        setup_by_user_id: int,
        setup_by_username: str | None = None,
        admin_role_ids: str | None = None,
    ) -> GuildConfig:
        """Create a new guild configuration."""
        guild_config = GuildConfig(
            guild_id=guild_id,
            guild_name=guild_name,
            verified_role_id=verified_role_id,
            setup_by_user_id=setup_by_user_id,
            setup_by_username=setup_by_username,
            admin_role_ids=admin_role_ids,
        )
        session.add(guild_config)
        try:
            await session.flush()
            logger.info(f"Created guild config for guild {guild_id} ({guild_name})")
            return guild_config
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating guild config: {e}")
            raise RecordAlreadyExistsError(
                "Guild configuration already exists",
                "This server has already been set up.",
            ) from e

    @staticmethod
    async def get_by_guild_id(
        session: AsyncSession, guild_id: int
    ) -> GuildConfig | None:
        """Get guild configuration by guild ID."""
        result = await session.execute(
            select(GuildConfig).where(GuildConfig.guild_id == guild_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all(session: AsyncSession) -> Sequence[GuildConfig]:
        """Get all guild configurations."""
        result = await session.execute(select(GuildConfig))
        return result.scalars().all()

    @staticmethod
    async def update(
        session: AsyncSession, guild_id: int, **kwargs
    ) -> GuildConfig | None:
        """Update guild configuration."""
        guild_config = await GuildConfigRepository.get_by_guild_id(session, guild_id)
        if not guild_config:
            return None

        for key, value in kwargs.items():
            if hasattr(guild_config, key):
                setattr(guild_config, key, value)

        await session.flush()
        logger.info(f"Updated guild config for guild {guild_id}")
        return guild_config

    @staticmethod
    async def delete(session: AsyncSession, guild_id: int) -> bool:
        """Delete guild configuration. Returns True if deleted, False if not found."""
        result = await session.execute(
            delete(GuildConfig).where(GuildConfig.guild_id == guild_id)
        )
        await session.flush()
        deleted: bool = result.rowcount > 0  # type: ignore[attr-defined]
        if deleted:
            logger.info(f"Deleted guild config for guild {guild_id}")
        return deleted
