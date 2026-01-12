"""Discord bot event handlers."""

import logging

import discord
from discord.ext import commands

from src.config import config
from src.database.connection import get_db_session
from src.database.repositories import GuildConfigRepository
from src.services.impersonation_detection_service import (
    impersonation_detection_service,
)
from src.services.impersonation_moderation_service import (
    impersonation_moderation_service,
)
from src.services.verification_service import verification_service

logger = logging.getLogger(__name__)


def setup_events(bot: commands.Bot) -> None:
    """Register event handlers."""

    @bot.event
    async def on_member_join(member: discord.Member):
        """
        Handle member join event.

        If the member is verified, reapply their nickname based on guild config.
        Note: Role is automatically assigned by Discord via Linked Roles.
        """
        try:
            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    member.guild.id,
                )

            if not guild_config:
                logger.debug(
                    f"Guild {member.guild.id} not configured, skipping member join handler"
                )
                return

            # Check if member is verified
            async with get_db_session() as db_session:
                verification = (
                    await verification_service.get_verification_by_discord_id(
                        db_session,
                        member.id,
                    )
                )

            if not verification:
                logger.debug(
                    f"Member {member.id} joined guild {member.guild.id} but is not verified"
                )
                return

            # Determine target nickname
            target_nickname = (
                verification.twitch_display_name or verification.twitch_username
            )

            # Update nickname if enforcement is enabled for this guild
            if (
                config.enable_nickname_enforcement
                and guild_config.nickname_enforcement_enabled
            ):
                try:
                    await member.edit(
                        nick=target_nickname,
                        reason="Verified user rejoined - reapplying nickname",
                    )
                    logger.info(
                        f"Reapplied nickname {target_nickname} to rejoined member {member.id} in guild {member.guild.id}"
                    )
                except discord.Forbidden:
                    logger.warning(
                        f"No permission to set nickname for member {member.id} in guild {member.guild.id}"
                    )
                except discord.HTTPException as e:
                    logger.error(
                        f"Failed to set nickname for member {member.id} in guild {member.guild.id}: {e}"
                    )

            # Check for impersonation (if enabled)
            if guild_config.impersonation_detection_enabled and not member.bot:
                try:
                    logger.debug(
                        f"Checking impersonation for new member {member.id} in guild {member.guild.id}"
                    )

                    async with get_db_session() as db_session:
                        detection = await impersonation_detection_service.check_user(
                            db_session,
                            member=member,
                            guild_id=member.guild.id,
                            guild_config=guild_config,
                            trigger="member_join",
                        )

                    if detection:
                        score = detection["scores"]["total_score"]
                        risk = detection["scores"]["risk_level"]

                        # Check if score meets threshold
                        if score >= guild_config.impersonation_min_score_threshold:
                            logger.warning(
                                f"Potential impersonation detected: {member.name} -> "
                                f"{detection['streamer'].twitch_username} "
                                f"(score: {score}, risk: {risk})"
                            )

                            # Send alert to moderation channel
                            await impersonation_moderation_service.send_alert(
                                member.guild,
                                detection["detection"],
                                guild_config,
                            )

                            # Apply handling strategies
                            if guild_config.impersonation_auto_quarantine_enabled:
                                await impersonation_moderation_service.apply_quarantine(
                                    member, guild_config
                                )

                            if guild_config.impersonation_auto_dm_enabled:
                                await impersonation_moderation_service.send_dm_to_user(
                                    member, member.guild, detection["detection"]
                                )
                        else:
                            logger.debug(
                                f"Detection score {score} below threshold "
                                f"({guild_config.impersonation_min_score_threshold}), not alerting"
                            )

                except Exception as e:
                    logger.error(
                        f"Error checking impersonation for member {member.id} in guild {member.guild.id}: {e}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(
                f"Error in on_member_join for member {member.id} in guild {member.guild.id}: {e}",
                exc_info=True,
            )

    logger.info("Event handlers registered")
