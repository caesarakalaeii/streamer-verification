"""SQLAlchemy ORM models for database tables."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Index, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class UserVerification(Base):
    """Main verification table: Enforces 1-to-1 mapping between Discord and Twitch users."""

    __tablename__ = "user_verifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    twitch_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    twitch_username: Mapped[str] = mapped_column(String(255), nullable=False)
    twitch_display_name: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_nickname_check: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_nickname_update: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserVerification(discord_user_id={self.discord_user_id}, twitch_username='{self.twitch_username}')>"


class OAuthSession(Base):
    """OAuth session tracking: Prevents link sharing via dual OAuth flow."""

    __tablename__ = "oauth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    discord_username: Mapped[str] = mapped_column(String(255), nullable=False)
    discord_guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, index=True)

    # Step 1: Discord OAuth (Identity Verification)
    discord_oauth_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discord_oauth_verified_id: Mapped[int | None] = mapped_column(BigInteger)
    discord_oauth_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    # Step 2: Twitch OAuth (Account Linking)
    twitch_oauth_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    twitch_user_id: Mapped[str | None] = mapped_column(String(255))
    twitch_username: Mapped[str | None] = mapped_column(String(255))
    twitch_oauth_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_oauth_expires", "expires_at", postgresql_where=~twitch_oauth_completed),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<OAuthSession(token='{self.token[:8]}...', discord_user_id={self.discord_user_id})>"


class GuildConfig(Base):
    """Guild configuration: Per-server settings."""

    __tablename__ = "guild_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    guild_name: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    admin_role_ids: Mapped[str | None] = mapped_column(Text)
    nickname_enforcement_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_role_assignment_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    nickname_check_interval_seconds: Mapped[int] = mapped_column(default=300, nullable=False)
    setup_completed_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    setup_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    setup_by_username: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """String representation."""
        return f"<GuildConfig(guild_id={self.guild_id}, guild_name='{self.guild_name}')>"


class VerificationAuditLog(Base):
    """Audit log for security monitoring and debugging."""

    __tablename__ = "verification_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    discord_username: Mapped[str | None] = mapped_column(String(255))
    discord_guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    twitch_user_id: Mapped[str | None] = mapped_column(String(255))
    twitch_username: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        """String representation."""
        return f"<VerificationAuditLog(action='{self.action}', discord_user_id={self.discord_user_id})>"
