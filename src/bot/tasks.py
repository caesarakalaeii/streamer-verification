"""Discord bot periodic tasks."""

import asyncio
import logging

import discord
from discord.ext import commands, tasks

from src.config import config
from src.database.connection import get_db_session
from src.database.repositories import (
    GuildConfigRepository,
    OAuthSessionRepository,
    StreamerCacheRepository,
    UserVerificationRepository,
    VerificationAuditLogRepository,
)
from src.services.impersonation_detection_service import (
    impersonation_detection_service,
)
from src.services.verification_service import verification_service
from src.shared.constants import AUDIT_ACTION_NICKNAME_UPDATED

logger = logging.getLogger(__name__)

# Track users we've already DM'd to avoid spam
_dm_sent_users: set[int] = set()


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
                verifications = await verification_service.get_all_verifications(
                    db_session
                )

            logger.debug(
                f"Checking nicknames for {len(verifications)} verified users across {len(guild_configs)} guilds"
            )

            # Process each guild
            for guild_config in guild_configs:
                if not guild_config.nickname_enforcement_enabled:
                    logger.debug(
                        f"Nickname enforcement disabled for guild {guild_config.guild_id}, skipping"
                    )
                    continue

                guild = bot.get_guild(guild_config.guild_id)
                if not guild:
                    logger.warning(
                        f"Guild {guild_config.guild_id} not found (bot may have been removed)"
                    )
                    continue

                # Check each verification for members in this guild
                for verification in verifications:
                    try:
                        member = guild.get_member(verification.discord_user_id)
                        if not member:
                            continue  # User not in this guild

                        # Determine target nickname
                        target_nickname = (
                            verification.twitch_display_name
                            or verification.twitch_username
                        )

                        # Check if nickname needs update
                        if member.nick != target_nickname:
                            if not config.dry_run_mode:
                                try:
                                    await member.edit(
                                        nick=target_nickname,
                                        reason="Twitch verification enforcement",
                                    )

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

                                    logger.info(
                                        f"Updated nickname for {member.id} to {target_nickname} in guild {guild.id}"
                                    )
                                except discord.Forbidden:
                                    logger.warning(
                                        f"No permission to update nickname for {member.id} in guild {guild.id}"
                                    )
                                except discord.HTTPException as e:
                                    logger.error(
                                        f"Failed to update nickname for {member.id} in guild {guild.id}: {e}"
                                    )
                            else:
                                logger.info(
                                    f"[DRY RUN] Would update nickname for {member.id} to {target_nickname} in guild {guild.id}"
                                )
                        else:
                            # Nickname is correct, just update check timestamp
                            async with get_db_session() as db_session:
                                await UserVerificationRepository.update_nickname_check(
                                    db_session,
                                    verification.id,
                                )

                    except Exception as e:
                        logger.error(
                            f"Error enforcing nickname for {verification.discord_user_id} in guild {guild.id}: {e}",
                            exc_info=True,
                        )

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
                deleted_count = await OAuthSessionRepository.cleanup_expired_sessions(
                    db_session
                )

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired OAuth sessions")

        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}", exc_info=True)

    @tasks.loop(minutes=10)
    async def check_role_verification_mismatch():
        """
        Periodically check for users who have the verified role but aren't in the database.

        This catches cases where:
        - User was unverified but Discord Linked Roles auto-reassigned the role
        - User manually got the role without verification
        - Database and Discord roles are out of sync

        For these users, we remove the role and send a DM with verification instructions.
        """
        try:
            # Get all guild configurations
            async with get_db_session() as db_session:
                guild_configs = await GuildConfigRepository.get_all(db_session)

            if not guild_configs:
                logger.debug(
                    "No guilds configured yet, skipping role verification mismatch check"
                )
                return

            # Get all verified users from database
            async with get_db_session() as db_session:
                verifications = await verification_service.get_all_verifications(
                    db_session
                )

            verified_user_ids = {v.discord_user_id for v in verifications}

            logger.debug(
                f"Checking role/verification mismatches in {len(guild_configs)} guilds"
            )

            # Process each guild
            for guild_config in guild_configs:
                if not guild_config.auto_role_assignment_enabled:
                    logger.debug(
                        "Auto role assignment disabled for guild %s, skipping mismatch check",
                        guild_config.guild_id,
                    )
                    continue

                guild = bot.get_guild(guild_config.guild_id)
                if not guild:
                    logger.warning(
                        f"Guild {guild_config.guild_id} not found (bot may have been removed)"
                    )
                    continue

                role = guild.get_role(guild_config.verified_role_id)
                if not role:
                    logger.warning(
                        f"Verified role {guild_config.verified_role_id} not found in guild {guild.id}"
                    )
                    continue

                # Check all members with the verified role
                for member in role.members:
                    # Skip if user is actually verified
                    if member.id in verified_user_ids:
                        continue

                    # User has role but no verification record!
                    logger.warning(
                        f"User {member.id} has verified role in guild {guild.id} but no verification record"
                    )

                    try:
                        # Remove the role
                        await member.remove_roles(
                            role,
                            reason="Not verified - role/database mismatch detected",
                        )
                        logger.info(
                            f"Removed verified role from {member.id} in guild {guild.id} (not verified)"
                        )

                        # Send DM with verification instructions (once per user, not per guild)
                        if member.id not in _dm_sent_users:
                            try:
                                embed = discord.Embed(
                                    title="🔒 Verification Required",
                                    description=f"Your verified role was removed in **{guild.name}** because you're not currently verified.",
                                    color=discord.Color.orange(),
                                )

                                embed.add_field(
                                    name="Why did this happen?",
                                    value="You need to link your Twitch account through Discord's Connections to get verified.",
                                    inline=False,
                                )

                                embed.add_field(
                                    name="How to verify:",
                                    value=(
                                        "1. Go to **Discord Settings** → **Connections**\n"
                                        "2. Find and click **Link** on the verification app\n"
                                        "3. Authenticate with Twitch\n"
                                        "4. Your role will be automatically assigned!"
                                    ),
                                    inline=False,
                                )

                                embed.set_footer(
                                    text=f"Server: {guild.name} • Verification is required"
                                )

                                await member.send(embed=embed)
                                _dm_sent_users.add(member.id)
                                logger.info(
                                    f"Sent verification instructions DM to user {member.id}"
                                )

                            except discord.Forbidden:
                                logger.warning(
                                    f"Cannot send DM to user {member.id} (DMs disabled)"
                                )
                            except discord.HTTPException as e:
                                logger.error(
                                    f"Failed to send DM to user {member.id}: {e}"
                                )

                    except discord.Forbidden:
                        logger.warning(
                            f"No permission to remove role from user {member.id} in guild {guild.id}"
                        )
                    except discord.HTTPException as e:
                        logger.error(
                            f"Failed to remove role from user {member.id} in guild {guild.id}: {e}"
                        )

        except Exception as e:
            logger.error(
                f"Error in role verification mismatch check: {e}", exc_info=True
            )

    @tasks.loop(hours=24)
    async def check_impersonation_daily():
        """
        Daily check for impersonation across all guild members.

        Checks all members in configured guilds for potential impersonation attempts.
        Runs at 2 AM UTC to avoid peak hours.
        """
        try:
            # Get all guild configurations with impersonation detection enabled
            async with get_db_session() as db_session:
                guild_configs = await GuildConfigRepository.get_all(db_session)

            if not guild_configs:
                logger.debug("No guilds configured, skipping impersonation check")
                return

            # Filter guilds with impersonation detection enabled
            enabled_guilds = [
                gc for gc in guild_configs if gc.impersonation_detection_enabled
            ]

            if not enabled_guilds:
                logger.debug(
                    "No guilds with impersonation detection enabled, skipping check"
                )
                return

            logger.info(
                f"Starting daily impersonation check for {len(enabled_guilds)} guilds"
            )

            # Process each guild
            for guild_config in enabled_guilds:
                guild = bot.get_guild(guild_config.guild_id)
                if not guild:
                    logger.warning(
                        f"Guild {guild_config.guild_id} not found (bot may have been removed)"
                    )
                    continue

                logger.info(
                    f"Checking impersonation in guild {guild.name} ({guild.id})"
                )

                # Get all members in batches
                members = list(guild.members)
                batch_size = 50
                checked = 0
                detected = 0

                for i in range(0, len(members), batch_size):
                    batch = members[i : i + batch_size]

                    for member in batch:
                        # Skip bots
                        if member.bot:
                            continue

                        # Skip verified users (they're legitimate)
                        async with get_db_session() as db_session:
                            verification = await verification_service.get_verification_by_discord_id(
                                db_session, member.id
                            )
                        if verification:
                            continue

                        # Check for impersonation
                        async with get_db_session() as db_session:
                            detection = (
                                await impersonation_detection_service.check_user(
                                    db_session,
                                    member=member,
                                    guild_id=guild.id,
                                    guild_config=guild_config,
                                    trigger="daily_check",
                                )
                            )

                        if detection:
                            detected += 1
                            # Alert will be sent by the moderation service if configured
                            logger.info(
                                f"Detected potential impersonation: {member.name} (score: {detection['scores']['total_score']})"
                            )

                        checked += 1

                    # Rate limit: wait between batches
                    await asyncio.sleep(5)

                logger.info(
                    f"Completed impersonation check for {guild.name}: checked {checked} members, detected {detected}"
                )

        except Exception as e:
            logger.error(f"Error in daily impersonation check: {e}", exc_info=True)

    @tasks.loop(hours=24)
    async def refresh_streamer_cache():
        """
        Refresh stale streamer cache entries.

        Updates cache entries older than 7 days with fresh data from Twitch API.
        Runs every 24 hours.
        """
        try:
            async with get_db_session() as db_session:
                # Get stale cache entries (older than 7 days)
                stale_entries = await StreamerCacheRepository.get_stale_entries(
                    db_session, days_old=7
                )

            if not stale_entries:
                logger.debug("No stale streamer cache entries found")
                return

            logger.info(f"Refreshing {len(stale_entries)} stale streamer cache entries")

            # Refresh in batches (Twitch rate limit: 800 requests/min)
            batch_size = 100
            refreshed = 0
            failed = 0

            for i in range(0, len(stale_entries), batch_size):
                batch = stale_entries[i : i + batch_size]

                for entry in batch:
                    async with get_db_session() as db_session:
                        success = await impersonation_detection_service.refresh_streamer_cache(
                            db_session, entry.twitch_user_id
                        )

                    if success:
                        refreshed += 1
                    else:
                        failed += 1

                    # Rate limiting (0.1s per request = max 600 req/min, well under 800 limit)
                    await asyncio.sleep(0.1)

                # Longer pause between batches
                await asyncio.sleep(5)

            logger.info(
                f"Streamer cache refresh complete: {refreshed} refreshed, {failed} failed"
            )

        except Exception as e:
            logger.error(f"Error in streamer cache refresh: {e}", exc_info=True)

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

    @check_role_verification_mismatch.before_loop
    async def before_check_role_verification_mismatch():
        """Wait until bot is ready before starting role verification mismatch check."""
        await bot.wait_until_ready()
        logger.info("Starting role verification mismatch check task")

    @check_impersonation_daily.before_loop
    async def before_check_impersonation_daily():
        """Wait until bot is ready before starting daily impersonation check."""
        await bot.wait_until_ready()
        logger.info("Starting daily impersonation check task")

    @refresh_streamer_cache.before_loop
    async def before_refresh_streamer_cache():
        """Wait until bot is ready before starting streamer cache refresh."""
        await bot.wait_until_ready()
        logger.info("Starting streamer cache refresh task")

    # Start tasks
    enforce_nicknames.start()
    cleanup_expired_sessions.start()
    check_role_verification_mismatch.start()
    check_impersonation_daily.start()
    refresh_streamer_cache.start()

    logger.info("Periodic tasks registered and started")
