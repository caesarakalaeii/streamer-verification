"""Service for handling immediate post-verification actions (role & nickname assignment)."""

import logging

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.bot_instance import get_bot_instance
from src.database.repositories import GuildConfigRepository

logger = logging.getLogger(__name__)


class PostVerificationService:
    """Service for immediate role and nickname assignment after verification."""

    @staticmethod
    async def assign_role_and_nickname(
        db_session: AsyncSession,
        discord_user_id: int,
        twitch_username: str,
        twitch_display_name: str | None = None,
    ) -> None:
        """
        Immediately assign verified role and set nickname after successful verification.

        This is called right after the OAuth flow completes to provide immediate
        feedback to the user, rather than waiting for periodic enforcement tasks.

        Args:
            db_session: Database session
            discord_user_id: Discord user ID
            twitch_username: Twitch username
            twitch_display_name: Twitch display name (fallback to username if None)
        """
        bot = get_bot_instance()
        if not bot:
            logger.warning(
                "Bot instance not available, skipping immediate role/nickname assignment"
            )
            return

        target_nickname = twitch_display_name or twitch_username

        # Find all guilds where the user is a member and bot is configured
        guilds_processed = 0
        for guild in bot.guilds:
            try:
                # Check if user is a member of this guild
                member = guild.get_member(discord_user_id)
                if not member:
                    continue

                # Check if guild is configured
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    guild.id,
                )
                if not guild_config:
                    logger.debug(
                        f"Guild {guild.id} ({guild.name}) not configured, skipping"
                    )
                    continue

                # Assign verified role
                role = guild.get_role(guild_config.verified_role_id)
                if role:
                    if role not in member.roles:
                        try:
                            await member.add_roles(
                                role, reason="Twitch verification complete"
                            )
                            logger.info(
                                f"✅ Assigned role {role.name} to {member.id} in guild {guild.id} ({guild.name})"
                            )
                        except discord.Forbidden:
                            logger.warning(
                                f"No permission to assign role {role.name} to {member.id} in guild {guild.id}"
                            )
                        except discord.HTTPException as e:
                            logger.error(
                                f"Failed to assign role {role.name} to {member.id} in guild {guild.id}: {e}"
                            )
                    else:
                        logger.debug(
                            f"User {member.id} already has role {role.name} in guild {guild.id}"
                        )
                else:
                    logger.warning(
                        f"Configured verified role {guild_config.verified_role_id} not found in guild {guild.id}"
                    )

                # Set nickname if enforcement is enabled
                if guild_config.nickname_enforcement_enabled:
                    if member.nick != target_nickname:
                        try:
                            await member.edit(
                                nick=target_nickname,
                                reason="Twitch verification complete",
                            )
                            logger.info(
                                f"✅ Set nickname to '{target_nickname}' for {member.id} in guild {guild.id} ({guild.name})"
                            )
                        except discord.Forbidden:
                            logger.warning(
                                f"No permission to set nickname for {member.id} in guild {guild.id}"
                            )
                        except discord.HTTPException as e:
                            logger.error(
                                f"Failed to set nickname for {member.id} in guild {guild.id}: {e}"
                            )
                    else:
                        logger.debug(
                            f"User {member.id} already has correct nickname '{target_nickname}' in guild {guild.id}"
                        )

                guilds_processed += 1

            except Exception as e:
                logger.error(
                    f"Error processing guild {guild.id} for user {discord_user_id}: {e}",
                    exc_info=True,
                )

        if guilds_processed == 0:
            logger.info(
                f"User {discord_user_id} verified but not in any configured guilds (will be processed when they join)"
            )
        else:
            logger.info(
                f"Processed immediate role/nickname assignment for user {discord_user_id} in {guilds_processed} guild(s)"
            )


# Global instance
post_verification_service = PostVerificationService()
