"""Data access layer (repositories) for database operations."""

import logging
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import config
from src.database.models import (
    GuildConfig,
    ImpersonationDetection,
    ImpersonationWhitelist,
    OAuthSession,
    StreamerCache,
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


class StreamerCacheRepository:
    """Repository for StreamerCache table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        twitch_user_id: str,
        twitch_username: str,
        twitch_display_name: str | None = None,
        follower_count: int = 0,
        description: str | None = None,
        has_discord_link: bool = False,
        profile_image_url: str | None = None,
        profile_image_hash: int | None = None,
    ) -> StreamerCache:
        """Create a new streamer cache entry."""
        cache_entry = StreamerCache(
            twitch_user_id=twitch_user_id,
            twitch_username=twitch_username,
            twitch_display_name=twitch_display_name,
            follower_count=follower_count,
            description=description,
            has_discord_link=has_discord_link,
            profile_image_url=profile_image_url,
            profile_image_hash=profile_image_hash,
            cached_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
        )
        session.add(cache_entry)
        try:
            await session.flush()
            logger.info(f"Created streamer cache entry for {twitch_username}")
            return cache_entry
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating streamer cache: {e}")
            raise RecordAlreadyExistsError(
                "Streamer cache entry already exists",
                "This Twitch user is already cached.",
            ) from e

    @staticmethod
    async def get_by_twitch_id(
        session: AsyncSession, twitch_user_id: str
    ) -> StreamerCache | None:
        """Get streamer cache entry by Twitch user ID."""
        result = await session.execute(
            select(StreamerCache).where(StreamerCache.twitch_user_id == twitch_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        session: AsyncSession, twitch_username: str
    ) -> StreamerCache | None:
        """Get streamer cache entry by Twitch username (case-insensitive)."""
        result = await session.execute(
            select(StreamerCache).where(
                StreamerCache.twitch_username.ilike(twitch_username)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_cached(session: AsyncSession) -> Sequence[StreamerCache]:
        """
        Get all cached streamers.

        WARNING: This loads all streamers into memory. For detection checks,
        use get_candidates_for_username() instead for better performance.
        """
        result = await session.execute(select(StreamerCache))
        return result.scalars().all()

    @staticmethod
    async def get_candidates_for_username(
        session: AsyncSession, username: str, limit: int = 50
    ) -> Sequence[StreamerCache]:
        """
        Get candidate streamers for similarity checking based on username.

        Uses length-based pre-filtering to avoid loading all streamers into memory.
        Only returns streamers with similar username lengths (±3 characters).

        Args:
            session: Database session
            username: Username to find candidates for
            limit: Maximum number of candidates to return

        Returns:
            Streamers with similar username lengths, ordered by most recently updated
        """
        username_len = len(username)
        min_len = max(3, username_len - 3)  # Minimum 3 chars
        max_len = username_len + 3

        result = await session.execute(
            select(StreamerCache)
            .where(
                # Length-based pre-filter (uses function index if available)
                StreamerCache.twitch_username.op("~")(f"^.{{{min_len},{max_len}}}$")
            )
            .order_by(StreamerCache.last_updated.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def search_by_similarity(
        session: AsyncSession,
        username: str,
        limit: int = 50,
        min_similarity: float = 0.3,
    ) -> Sequence[StreamerCache]:
        """Find candidate streamers using PostgreSQL trigram similarity."""

        if not username:
            return []

        username_len = len(username)
        min_len = max(3, username_len - 3)
        max_len = username_len + 3

        similarity_expr = func.similarity(StreamerCache.twitch_username, username)

        stmt = (
            select(StreamerCache)
            .where(
                StreamerCache.twitch_username.op("~")(f"^.{{{min_len},{max_len}}}$"),
                StreamerCache.twitch_username.op("%")(username),
                similarity_expr >= min_similarity,
            )
            .order_by(similarity_expr.desc(), StreamerCache.last_updated.desc())
            .limit(limit)
        )

        try:
            result = await session.execute(stmt)
            matches = result.scalars().all()
            if matches:
                return matches
        except ProgrammingError as exc:  # Extension not installed yet
            logger.warning(
                "pg_trgm extension unavailable, falling back to length-based search: %s",
                exc,
            )

        return await StreamerCacheRepository.get_candidates_for_username(
            session, username, limit
        )

    @staticmethod
    async def get_stale_entries(
        session: AsyncSession, days_old: int = 7
    ) -> Sequence[StreamerCache]:
        """Get cache entries older than specified days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        result = await session.execute(
            select(StreamerCache).where(StreamerCache.last_updated < cutoff_date)
        )
        return result.scalars().all()

    @staticmethod
    async def update(
        session: AsyncSession,
        twitch_user_id: str,
        **kwargs,
    ) -> StreamerCache | None:
        """Update streamer cache entry."""
        cache_entry = await StreamerCacheRepository.get_by_twitch_id(
            session, twitch_user_id
        )
        if not cache_entry:
            return None

        for key, value in kwargs.items():
            if hasattr(cache_entry, key):
                setattr(cache_entry, key, value)

        cache_entry.last_updated = datetime.utcnow()
        await session.flush()
        logger.info(f"Updated streamer cache for {cache_entry.twitch_username}")
        return cache_entry

    @staticmethod
    async def increment_cache_hits(session: AsyncSession, twitch_user_id: str) -> None:
        """Increment cache hit counter."""
        await session.execute(
            update(StreamerCache)
            .where(StreamerCache.twitch_user_id == twitch_user_id)
            .values(cache_hits=StreamerCache.cache_hits + 1)
        )
        await session.flush()


class ImpersonationDetectionRepository:
    """Repository for ImpersonationDetection table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        guild_id: int,
        discord_user_id: int,
        discord_username: str,
        discord_display_name: str | None,
        discord_account_age_days: int,
        discord_bio: str | None,
        suspected_streamer_id: str,
        suspected_streamer_username: str,
        suspected_streamer_follower_count: int,
        total_score: int,
        username_similarity_score: int,
        account_age_score: int,
        bio_match_score: int,
        streamer_popularity_score: int,
        discord_absence_score: int,
        avatar_match_score: int,
        risk_level: str,
        detection_trigger: str | None = None,
    ) -> ImpersonationDetection:
        """Create a new impersonation detection record."""
        detection = ImpersonationDetection(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            discord_display_name=discord_display_name,
            discord_account_age_days=discord_account_age_days,
            discord_bio=discord_bio,
            suspected_streamer_id=suspected_streamer_id,
            suspected_streamer_username=suspected_streamer_username,
            suspected_streamer_follower_count=suspected_streamer_follower_count,
            total_score=total_score,
            username_similarity_score=username_similarity_score,
            account_age_score=account_age_score,
            bio_match_score=bio_match_score,
            streamer_popularity_score=streamer_popularity_score,
            discord_absence_score=discord_absence_score,
            avatar_match_score=avatar_match_score,
            risk_level=risk_level,
            detection_trigger=detection_trigger,
            detected_at=datetime.utcnow(),
        )
        session.add(detection)
        await session.flush()
        logger.info(
            f"Created impersonation detection for Discord user {discord_user_id} "
            f"(suspected: {suspected_streamer_username}, score: {total_score})"
        )
        return detection

    @staticmethod
    async def get_by_id(
        session: AsyncSession, detection_id: int
    ) -> ImpersonationDetection | None:
        """Get detection by ID."""
        result = await session.execute(
            select(ImpersonationDetection).where(
                ImpersonationDetection.id == detection_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_and_guild(
        session: AsyncSession, discord_user_id: int, guild_id: int
    ) -> ImpersonationDetection | None:
        """Get most recent detection for a user in a guild."""
        result = await session.execute(
            select(ImpersonationDetection)
            .where(
                ImpersonationDetection.discord_user_id == discord_user_id,
                ImpersonationDetection.guild_id == guild_id,
            )
            .order_by(ImpersonationDetection.detected_at.desc())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pending_by_guild(
        session: AsyncSession, guild_id: int, limit: int = 100
    ) -> Sequence[ImpersonationDetection]:
        """Get pending (unreviewed) detections for a guild."""
        result = await session.execute(
            select(ImpersonationDetection)
            .where(
                ImpersonationDetection.guild_id == guild_id,
                ImpersonationDetection.status == "pending",
            )
            .order_by(
                ImpersonationDetection.total_score.desc(),
                ImpersonationDetection.detected_at.desc(),
            )
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_by_guild_and_status(
        session: AsyncSession, guild_id: int, status: str, limit: int = 100
    ) -> Sequence[ImpersonationDetection]:
        """Get detections by guild and status."""
        result = await session.execute(
            select(ImpersonationDetection)
            .where(
                ImpersonationDetection.guild_id == guild_id,
                ImpersonationDetection.status == status,
            )
            .order_by(ImpersonationDetection.detected_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def update_status(
        session: AsyncSession,
        detection_id: int,
        status: str,
        reviewed_by_user_id: int,
        reviewed_by_username: str,
        moderator_action: str | None = None,
        moderator_notes: str | None = None,
    ) -> ImpersonationDetection | None:
        """Update detection status after moderation."""
        detection = await ImpersonationDetectionRepository.get_by_id(
            session, detection_id
        )
        if not detection:
            return None

        detection.status = status
        detection.reviewed_by_user_id = reviewed_by_user_id
        detection.reviewed_by_username = reviewed_by_username
        detection.reviewed_at = datetime.utcnow()
        if moderator_action:
            detection.moderator_action = moderator_action
        if moderator_notes:
            detection.moderator_notes = moderator_notes

        await session.flush()
        logger.info(
            f"Updated detection {detection_id} status to {status} by {reviewed_by_username}"
        )
        return detection

    @staticmethod
    async def set_alert_message_id(
        session: AsyncSession, detection_id: int, message_id: int
    ) -> None:
        """Set the alert message ID for a detection."""
        await session.execute(
            update(ImpersonationDetection)
            .where(ImpersonationDetection.id == detection_id)
            .values(alert_message_id=message_id)
        )
        await session.flush()

    @staticmethod
    async def get_stats(
        session: AsyncSession, guild_id: int, days: int = 7
    ) -> dict[str, int]:
        """Get detection statistics for a guild."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get total detections
        total_result = await session.execute(
            select(ImpersonationDetection).where(
                ImpersonationDetection.guild_id == guild_id,
                ImpersonationDetection.detected_at >= cutoff_date,
            )
        )
        total = len(total_result.scalars().all())

        # Get pending count
        pending_result = await session.execute(
            select(ImpersonationDetection).where(
                ImpersonationDetection.guild_id == guild_id,
                ImpersonationDetection.status == "pending",
            )
        )
        pending = len(pending_result.scalars().all())

        # Get actions taken
        actioned_result = await session.execute(
            select(ImpersonationDetection).where(
                ImpersonationDetection.guild_id == guild_id,
                ImpersonationDetection.detected_at >= cutoff_date,
                ImpersonationDetection.moderator_action.isnot(None),
            )
        )
        actioned = len(actioned_result.scalars().all())

        return {
            "total_detections": total,
            "pending_reviews": pending,
            "actions_taken": actioned,
        }


class ImpersonationWhitelistRepository:
    """Repository for ImpersonationWhitelist table."""

    @staticmethod
    async def create(
        session: AsyncSession,
        guild_id: int,
        discord_user_id: int,
        discord_username: str,
        added_by_user_id: int,
        added_by_username: str,
        reason: str | None = None,
    ) -> ImpersonationWhitelist:
        """Add a user to the whitelist."""
        whitelist_entry = ImpersonationWhitelist(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            reason=reason,
            added_by_user_id=added_by_user_id,
            added_by_username=added_by_username,
        )
        session.add(whitelist_entry)
        try:
            await session.flush()
            logger.info(
                f"Added Discord user {discord_user_id} to whitelist in guild {guild_id}"
            )
            return whitelist_entry
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Integrity error creating whitelist entry: {e}")
            raise RecordAlreadyExistsError(
                "User already whitelisted",
                "This user is already on the whitelist for this server.",
            ) from e

    @staticmethod
    async def is_whitelisted(
        session: AsyncSession, discord_user_id: int, guild_id: int
    ) -> bool:
        """Check if a user is whitelisted in a guild."""
        result = await session.execute(
            select(ImpersonationWhitelist).where(
                ImpersonationWhitelist.discord_user_id == discord_user_id,
                ImpersonationWhitelist.guild_id == guild_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_by_guild(
        session: AsyncSession, guild_id: int
    ) -> Sequence[ImpersonationWhitelist]:
        """Get all whitelisted users for a guild."""
        result = await session.execute(
            select(ImpersonationWhitelist)
            .where(ImpersonationWhitelist.guild_id == guild_id)
            .order_by(ImpersonationWhitelist.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def delete(
        session: AsyncSession, discord_user_id: int, guild_id: int
    ) -> bool:
        """Remove a user from the whitelist. Returns True if deleted, False if not found."""
        result = await session.execute(
            delete(ImpersonationWhitelist).where(
                ImpersonationWhitelist.discord_user_id == discord_user_id,
                ImpersonationWhitelist.guild_id == guild_id,
            )
        )
        await session.flush()
        deleted: bool = result.rowcount > 0  # type: ignore[attr-defined]
        if deleted:
            logger.info(
                f"Removed Discord user {discord_user_id} from whitelist in guild {guild_id}"
            )
        return deleted
