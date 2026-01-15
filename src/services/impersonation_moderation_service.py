"""Moderation service for handling impersonation detection alerts and actions."""

import logging

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_db_session
from src.database.models import GuildConfig, ImpersonationDetection
from src.database.repositories import (
    ImpersonationDetectionRepository,
    ImpersonationWhitelistRepository,
    VerificationAuditLogRepository,
)
from src.shared.constants import (
    AUDIT_ACTION_IMPERSONATION_BANNED,
    AUDIT_ACTION_IMPERSONATION_FALSE_POSITIVE,
    AUDIT_ACTION_IMPERSONATION_KICKED,
    AUDIT_ACTION_IMPERSONATION_MARKED_SAFE,
    AUDIT_ACTION_IMPERSONATION_WARNED,
)

logger = logging.getLogger(__name__)


class ImpersonationModerationService:
    """Service for moderation actions on impersonation detections."""

    @staticmethod
    async def create_alert_embed(
        detection: ImpersonationDetection, member: discord.Member | None = None
    ) -> discord.Embed:
        """
        Create a rich embed for impersonation alert.

        Args:
            detection: Detection record from database
            member: Discord member object (optional, fetched if needed)

        Returns:
            Discord embed with detection details
        """
        # Determine color based on risk level
        color_map = {
            "critical": discord.Color.dark_red(),  # Dark red
            "high": discord.Color.red(),  # Red
            "medium": discord.Color.orange(),  # Orange
            "low": discord.Color.gold(),  # Gold
        }
        embed_color = color_map.get(detection.risk_level, discord.Color.orange())

        # Create embed
        embed = discord.Embed(
            title="🚨 Suspicious User Detected",
            description=f"Potential impersonation of **{detection.suspected_streamer_username}**",
            color=embed_color,
        )

        # User information
        account_age_days = detection.discord_account_age_days
        age_text = f"{account_age_days} day{'s' if account_age_days != 1 else ''}"

        user_info = (
            f"**Username:** {detection.discord_username}\n"
            f"**User ID:** {detection.discord_user_id}\n"
            f"**Mention:** <@{detection.discord_user_id}>\n"
            f"**Account Age:** {age_text}\n"
            f"**Twitch Verified:** ❌ No (Key Indicator!)"
        )
        embed.add_field(name="👤 User Information", value=user_info, inline=False)

        # Detection details
        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        risk_display = f"{risk_emoji.get(detection.risk_level, '⚪')} {detection.risk_level.upper()}"

        detection_info = (
            f"**Similarity Score:** ⚠️ {detection.total_score}/100 ({risk_display})\n"
            f"**Suspected Streamer:** {detection.suspected_streamer_username}\n"
            f"**Followers:** {detection.suspected_streamer_follower_count:,}"
        )
        embed.add_field(name="🔍 Detection Details", value=detection_info, inline=False)

        # Key indicators
        indicators = [
            "• **Not Twitch Verified** ❌ (Critical: Impersonators never verify)"
        ]
        if detection.username_similarity_score > 0:
            indicators.append(
                f"• Username Match: {detection.username_similarity_score}/40"
            )
        if detection.account_age_score > 0:
            indicators.append(f"• New Account: {detection.account_age_score}/20")
        if detection.bio_match_score > 0:
            indicators.append(f"• Bio Match: {detection.bio_match_score}/20")
        if detection.streamer_popularity_score > 0:
            indicators.append(
                f"• Target Range: {detection.streamer_popularity_score}/10"
            )
        if detection.discord_absence_score > 0:
            indicators.append(
                f"• No Discord Link: {detection.discord_absence_score}/10"
            )
        if detection.avatar_match_score > 0:
            indicators.append(
                f"• Avatar Match: {detection.avatar_match_score}/10"
            )

        if indicators:
            embed.add_field(
                name="📊 Key Indicators",
                value="\n".join(indicators),
                inline=False,
            )

        # Recommended action
        if detection.risk_level == "critical":
            recommendation = (
                "🔴 **Immediate review recommended** - Very high confidence"
            )
        elif detection.risk_level == "high":
            recommendation = "🟠 **Review recommended** - High confidence"
        elif detection.risk_level == "medium":
            recommendation = "🟡 **Monitor** - Moderate suspicion"
        else:
            recommendation = "🟢 **Low priority** - Minor similarity"

        embed.add_field(
            name="💡 Recommended Action", value=recommendation, inline=False
        )

        # Footer
        trigger_text = detection.detection_trigger or "unknown"
        embed.set_footer(
            text=f"Detection ID: {detection.id} | Trigger: {trigger_text} | Detected"
        )
        embed.timestamp = detection.detected_at

        return embed

    @staticmethod
    async def send_alert(
        guild: discord.Guild,
        detection: ImpersonationDetection,
        guild_config: GuildConfig,
    ) -> discord.Message | None:
        """
        Send impersonation alert to moderation channel.

        Args:
            guild: Discord guild
            detection: Detection record
            guild_config: Guild configuration

        Returns:
            Sent message or None if failed
        """
        if not guild_config.impersonation_moderation_channel_id:
            logger.warning(
                f"No moderation channel configured for guild {guild.id}, skipping alert"
            )
            return None

        moderation_channel = guild.get_channel(
            guild_config.impersonation_moderation_channel_id
        )
        if not moderation_channel or not isinstance(
            moderation_channel, discord.TextChannel
        ):
            logger.error(
                f"Moderation channel {guild_config.impersonation_moderation_channel_id} not found or not a text channel"
            )
            return None

        try:
            # Get member
            member = guild.get_member(detection.discord_user_id)

            # Create embed
            embed = await ImpersonationModerationService.create_alert_embed(
                detection, member
            )

            # Import view here to avoid circular imports
            from src.bot.interactions import ImpersonationAlertView

            # Create view with buttons
            view = ImpersonationAlertView(detection_id=detection.id)

            # Send message
            message = await moderation_channel.send(embed=embed, view=view)

            # Store message ID in detection
            async with get_db_session() as db_session:
                await ImpersonationDetectionRepository.set_alert_message_id(
                    db_session, detection.id, message.id
                )
                await db_session.commit()

            logger.info(
                f"Sent impersonation alert for detection {detection.id} to channel {moderation_channel.id}"
            )
            return message

        except discord.Forbidden:
            logger.error(
                f"No permission to send message to moderation channel {moderation_channel.id}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to send impersonation alert for detection {detection.id}: {e}",
                exc_info=True,
            )
            return None

    @staticmethod
    async def apply_quarantine(
        member: discord.Member, guild_config: GuildConfig
    ) -> bool:
        """
        Apply quarantine role to a member.

        Args:
            member: Discord member
            guild_config: Guild configuration with quarantine role

        Returns:
            True if successful, False otherwise
        """
        if not guild_config.impersonation_quarantine_role_id:
            logger.warning(f"No quarantine role configured for guild {member.guild.id}")
            return False

        quarantine_role = member.guild.get_role(
            guild_config.impersonation_quarantine_role_id
        )
        if not quarantine_role:
            logger.error(
                f"Quarantine role {guild_config.impersonation_quarantine_role_id} not found in guild {member.guild.id}"
            )
            return False

        try:
            await member.add_roles(
                quarantine_role, reason="Suspected impersonation - auto-quarantine"
            )
            logger.info(
                f"Applied quarantine role to {member.id} in guild {member.guild.id}"
            )
            return True
        except discord.Forbidden:
            logger.error(
                f"No permission to add quarantine role to {member.id} in guild {member.guild.id}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Failed to apply quarantine to {member.id}: {e}", exc_info=True
            )
            return False

    @staticmethod
    async def remove_quarantine(
        member: discord.Member, guild_config: GuildConfig
    ) -> bool:
        """
        Remove quarantine role from a member.

        Args:
            member: Discord member
            guild_config: Guild configuration with quarantine role

        Returns:
            True if successful, False otherwise
        """
        if not guild_config.impersonation_quarantine_role_id:
            return True  # No role to remove

        quarantine_role = member.guild.get_role(
            guild_config.impersonation_quarantine_role_id
        )
        if not quarantine_role:
            return True  # Role doesn't exist

        try:
            if quarantine_role in member.roles:
                await member.remove_roles(
                    quarantine_role, reason="Impersonation review completed"
                )
                logger.info(
                    f"Removed quarantine role from {member.id} in guild {member.guild.id}"
                )
            return True
        except discord.Forbidden:
            logger.error(
                f"No permission to remove quarantine role from {member.id} in guild {member.guild.id}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Failed to remove quarantine from {member.id}: {e}", exc_info=True
            )
            return False

    @staticmethod
    async def send_dm_to_user(
        member: discord.Member, guild: discord.Guild, detection: ImpersonationDetection
    ) -> bool:
        """
        Send DM to user explaining the detection.

        Args:
            member: Discord member
            guild: Discord guild
            detection: Detection record

        Returns:
            True if successful, False otherwise
        """
        try:
            embed = discord.Embed(
                title="🔍 Identity Verification Required",
                description="Our automated system has flagged your account for potential impersonation.",
                color=discord.Color.orange(),
            )

            embed.add_field(
                name="What happened?",
                value=f"Your username and profile closely resemble the Twitch streamer **{detection.suspected_streamer_username}**.",
                inline=False,
            )

            embed.add_field(
                name="If you are NOT impersonating anyone:",
                value=(
                    "1. Contact server moderators to explain\n"
                    "2. Consider changing your username/avatar if similar to the streamer\n"
                    "3. Wait for moderator review"
                ),
                inline=False,
            )

            embed.add_field(
                name="If you ARE the actual streamer:",
                value=(
                    "1. Verify your identity with server moderators\n"
                    "2. Use `/verify` to link your official Twitch account\n"
                    "3. This will prevent future flags"
                ),
                inline=False,
            )

            embed.set_footer(text=f"This is an automated message from {guild.name}")

            await member.send(embed=embed)
            logger.info(f"Sent impersonation DM to user {member.id}")
            return True

        except discord.Forbidden:
            logger.warning(
                f"Cannot send DM to user {member.id} (DMs disabled or blocked)"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to send DM to user {member.id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def execute_action(
        db_session: AsyncSession,
        detection: ImpersonationDetection,
        action: str,
        moderator: discord.Member,
        reason: str | None = None,
        notes: str | None = None,
    ) -> tuple[bool, str]:
        """
        Execute moderation action on a detection.

        Args:
            db_session: Database session
            detection: Detection record
            action: Action to take (ban, kick, warn, mark_safe, false_positive)
            moderator: Moderator taking action
            reason: Reason for action
            notes: Private moderator notes

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            guild = moderator.guild
            member = guild.get_member(detection.discord_user_id)

            if not member and action in ["ban", "kick", "warn"]:
                return False, "User is no longer in the server"

            # Execute action
            audit_action = None
            status = "reviewed_safe"
            moderator_action = action

            if action == "ban":
                if member:
                    await member.ban(
                        reason=reason or "Confirmed impersonation attempt",
                        delete_message_days=1,
                    )
                status = "actioned_ban"
                audit_action = AUDIT_ACTION_IMPERSONATION_BANNED
                message = f"Banned user {detection.discord_username}"

            elif action == "kick":
                if member:
                    await member.kick(reason=reason or "Suspected impersonation")
                status = "actioned_kick"
                audit_action = AUDIT_ACTION_IMPERSONATION_KICKED
                message = f"Kicked user {detection.discord_username}"

            elif action == "warn":
                # Send DM warning
                if member:
                    warning_embed = discord.Embed(
                        title="⚠️ Warning from Server Moderators",
                        description=f"You have been warned in **{guild.name}**",
                        color=discord.Color.orange(),
                    )
                    warning_embed.add_field(
                        name="Reason",
                        value=reason or "Suspected impersonation behavior",
                        inline=False,
                    )
                    warning_embed.add_field(
                        name="Action Required",
                        value="Please review your username and profile to avoid confusion with other users.",
                        inline=False,
                    )
                    try:
                        await member.send(embed=warning_embed)
                    except discord.Forbidden:
                        logger.warning(f"Could not DM warning to {member.id}")

                status = "actioned_warn"
                audit_action = AUDIT_ACTION_IMPERSONATION_WARNED
                message = f"Warned user {detection.discord_username}"

            elif action == "mark_safe":
                status = "reviewed_safe"
                audit_action = AUDIT_ACTION_IMPERSONATION_MARKED_SAFE
                message = f"Marked {detection.discord_username} as safe (false alarm)"

            elif action == "false_positive":
                # Add to whitelist
                await ImpersonationWhitelistRepository.create(
                    db_session,
                    guild_id=detection.guild_id,
                    discord_user_id=detection.discord_user_id,
                    discord_username=detection.discord_username,
                    added_by_user_id=moderator.id,
                    added_by_username=str(moderator),
                    reason=reason or "Marked as false positive",
                )
                status = "false_positive"
                audit_action = AUDIT_ACTION_IMPERSONATION_FALSE_POSITIVE
                message = f"Added {detection.discord_username} to whitelist"

            else:
                return False, f"Unknown action: {action}"

            # Update detection status
            await ImpersonationDetectionRepository.update_status(
                db_session,
                detection.id,
                status=status,
                reviewed_by_user_id=moderator.id,
                reviewed_by_username=str(moderator),
                moderator_action=moderator_action,
                moderator_notes=notes,
            )

            # Create audit log
            if audit_action:
                await VerificationAuditLogRepository.create(
                    db_session,
                    discord_user_id=detection.discord_user_id,
                    discord_username=detection.discord_username,
                    discord_guild_id=detection.guild_id,
                    action=audit_action,
                    reason=reason,
                )

            await db_session.commit()
            logger.info(
                f"Executed action '{action}' on detection {detection.id} by moderator {moderator.id}"
            )
            return True, message

        except discord.Forbidden as e:
            logger.error(f"Permission error executing action: {e}")
            await db_session.rollback()
            return False, "Bot lacks permissions to execute this action"
        except Exception as e:
            logger.error(
                f"Error executing action on detection {detection.id}: {e}",
                exc_info=True,
            )
            await db_session.rollback()
            return False, f"Error: {str(e)}"


# Global service instance
impersonation_moderation_service = ImpersonationModerationService()
