"""Discord bot periodic tasks."""

import logging

import discord
from discord.ext import commands, tasks

from src.config import config
from src.database.connection import get_db_session
from src.database.repositories import (
    GuildConfigRepository,
    OAuthSessionRepository,
    UserVerificationRepository,
    VerificationAuditLogRepository,
)
from src.services.verification_service import verification_service
from src.shared.constants import AUDIT_ACTION_NICKNAME_UPDATED

logger = logging.getLogger(__name__)


def setup_tasks(bot: commands.Bot) -> None:
    """Register periodic tasks."""

    @tasks.loop(seconds=config.nickname_check_interval_seconds)
    async def enforce_nicknames():
        """
        Periodically check and enforce verified user nicknames across all configured guilds.

        Runs every 5 minutes (default) to ensure all verified users have their
        nicknames set to their Twitch username in each guild they're in.
        """
        if not config.enable_nickname_enforcement:
            logger.debug("Nickname enforcement disabled globally, skipping")
            return

        try:
            # Get all guild configurations
            async with get_db_session() as db_session:
                guild_configs = await GuildConfigRepository.get_all(db_session)

            if not guild_configs:
                logger.debug("No guilds configured yet, skipping nickname enforcement")
                return

            # Get all verified users
            async with get_db_session() as db_session:
                verifications = await verification_service.get_all_verifications(db_session)

            logger.debug(f"Checking nicknames for {len(verifications)} verified users across {len(guild_configs)} guilds")

            # Process each guild
            for guild_config in guild_configs:
                if not guild_config.nickname_enforcement_enabled:
                    logger.debug(f"Nickname enforcement disabled for guild {guild_config.guild_id}, skipping")
                    continue

                guild = bot.get_guild(guild_config.guild_id)
                if not guild:
                    logger.warning(f"Guild {guild_config.guild_id} not found (bot may have been removed)")
                    continue

                # Check each verification for members in this guild
                for verification in verifications:
                    try:
                        member = guild.get_member(verification.discord_user_id)
                        if not member:
                            continue  # User not in this guild

                        # Determine target nickname
                        target_nickname = verification.twitch_display_name or verification.twitch_username

                        # Check if nickname needs update
                        if member.nick != target_nickname:
                            if not config.dry_run_mode:
                                try:
                                    await member.edit(nick=target_nickname, reason="Twitch verification enforcement")

                                    # Update database
                                    async with get_db_session() as db_session:
                                        await UserVerificationRepository.update_nickname_update(
                                            db_session,
                                            verification.id,
                                        )
                                        await VerificationAuditLogRepository.create(
                                            db_session,
                                            discord_user_id=verification.discord_user_id,
                                            discord_guild_id=guild.id,
                                            twitch_user_id=verification.twitch_user_id,
                                            twitch_username=verification.twitch_username,
                                            action=AUDIT_ACTION_NICKNAME_UPDATED,
                                        )

                                    logger.info(f"Updated nickname for {member.id} to {target_nickname} in guild {guild.id}")
                                except discord.Forbidden:
                                    logger.warning(f"No permission to update nickname for {member.id} in guild {guild.id}")
                                except discord.HTTPException as e:
                                    logger.error(f"Failed to update nickname for {member.id} in guild {guild.id}: {e}")
                            else:
                                logger.info(f"[DRY RUN] Would update nickname for {member.id} to {target_nickname} in guild {guild.id}")
                        else:
                            # Nickname is correct, just update check timestamp
                            async with get_db_session() as db_session:
                                await UserVerificationRepository.update_nickname_check(
                                    db_session,
                                    verification.id,
                                )

                    except Exception as e:
                        logger.error(f"Error enforcing nickname for {verification.discord_user_id} in guild {guild.id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in nickname enforcement task: {e}", exc_info=True)

    @tasks.loop(hours=config.session_cleanup_interval_hours)
    async def cleanup_expired_sessions():
        """
        Periodically clean up expired OAuth sessions.

        Runs every hour (configurable) to remove expired OAuth sessions from the database.
        """
        try:
            async with get_db_session() as db_session:
                deleted_count = await OAuthSessionRepository.cleanup_expired_sessions(db_session)

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired OAuth sessions")

        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}", exc_info=True)

    @enforce_nicknames.before_loop
    async def before_enforce_nicknames():
        """Wait until bot is ready before starting nickname enforcement task."""
        await bot.wait_until_ready()
        logger.info("Starting nickname enforcement task")

    @cleanup_expired_sessions.before_loop
    async def before_cleanup_sessions():
        """Wait until bot is ready before starting session cleanup task."""
        await bot.wait_until_ready()
        logger.info("Starting session cleanup task")

    # Start tasks
    enforce_nicknames.start()
    cleanup_expired_sessions.start()

    logger.info("Periodic tasks registered and started")
