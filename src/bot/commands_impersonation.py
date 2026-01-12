"""Slash commands for impersonation detection management."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.database.connection import get_db_session
from src.database.models import ImpersonationDetection
from src.database.repositories import (
    GuildConfigRepository,
    ImpersonationDetectionRepository,
    ImpersonationWhitelistRepository,
    StreamerCacheRepository,
)
from src.services.impersonation_detection_service import (
    impersonation_detection_service,
)
from src.services.impersonation_moderation_service import (
    impersonation_moderation_service,
)

logger = logging.getLogger(__name__)


def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user is admin (owner, administrator, or custom admin role)."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

    # Owner always has permission
    if interaction.user.id == interaction.guild.owner_id:
        return True

    # Check for administrator permission
    if interaction.user.guild_permissions.administrator:
        return True

    # Check custom admin roles (from guild config)
    # This will be checked in the command itself since we need DB access
    return False


def setup_impersonation_commands(bot: commands.Bot) -> None:
    """Register impersonation detection slash commands."""

    @bot.tree.command(
        name="impersonation-setup",
        description="Configure impersonation detection for this server",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        enabled="Enable or disable impersonation detection",
        moderation_channel="Channel to send alerts to",
        min_score="Minimum score to trigger alert (0-100, default: 60)",
        auto_quarantine="Enable automatic quarantine role assignment",
        quarantine_role="Role to assign for quarantine (required if auto_quarantine enabled)",
        auto_dm="Enable automatic DM to detected users",
        trusted_roles="Roles to trust (e.g., Discord's native Twitch verified role) - comma-separated mentions",
    )
    async def impersonation_setup(
        interaction: discord.Interaction,
        enabled: bool,
        moderation_channel: discord.TextChannel,
        min_score: int = 60,
        auto_quarantine: bool = False,
        quarantine_role: discord.Role | None = None,
        auto_dm: bool = False,
        trusted_roles: str | None = None,
    ):
        """Configure impersonation detection for the server."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure we're in a guild
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            # Validate min_score
            if not 0 <= min_score <= 100:
                await interaction.followup.send(
                    "❌ Minimum score must be between 0 and 100.", ephemeral=True
                )
                return

            # Validate quarantine settings
            if auto_quarantine and not quarantine_role:
                await interaction.followup.send(
                    "❌ Quarantine role is required when auto-quarantine is enabled.",
                    ephemeral=True,
                )
                return

            # Parse trusted role IDs
            trusted_role_ids_str = None
            if trusted_roles:
                # Extract role IDs from mentions or raw IDs
                import re

                role_ids = re.findall(r"<@&(\d+)>|(\d+)", trusted_roles)
                role_ids = [r[0] or r[1] for r in role_ids]
                trusted_role_ids_str = ",".join(role_ids)

            # Get or create guild config
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session, interaction.guild.id
                )

                if not guild_config:
                    await interaction.followup.send(
                        "❌ Server not configured. Please run `/setup` first.",
                        ephemeral=True,
                    )
                    return

                # Update impersonation settings
                await GuildConfigRepository.update(
                    db_session,
                    interaction.guild.id,
                    impersonation_detection_enabled=enabled,
                    impersonation_moderation_channel_id=moderation_channel.id,
                    impersonation_min_score_threshold=min_score,
                    impersonation_alert_only_enabled=not (auto_quarantine or auto_dm),
                    impersonation_auto_quarantine_enabled=auto_quarantine,
                    impersonation_quarantine_role_id=(
                        quarantine_role.id if quarantine_role else None
                    ),
                    impersonation_auto_dm_enabled=auto_dm,
                    impersonation_trusted_role_ids=trusted_role_ids_str,
                )

                await db_session.commit()

            # Create response embed
            embed = discord.Embed(
                title="✅ Impersonation Detection Configured",
                description="Your impersonation detection settings have been updated.",
                color=discord.Color.green(),
            )

            embed.add_field(
                name="Status",
                value=f"{'✅ Enabled' if enabled else '❌ Disabled'}",
                inline=True,
            )
            embed.add_field(
                name="Moderation Channel", value=moderation_channel.mention, inline=True
            )
            embed.add_field(
                name="Min Score Threshold", value=f"{min_score}/100", inline=True
            )

            strategies = []
            if not (auto_quarantine or auto_dm):
                strategies.append("• Alert Only (default)")
            if auto_quarantine:
                strategies.append(
                    f"• Auto-Quarantine ({quarantine_role.mention if quarantine_role else 'N/A'})"
                )
            if auto_dm:
                strategies.append("• Auto-DM Users")

            embed.add_field(
                name="Handling Strategies",
                value="\n".join(strategies) or "None",
                inline=False,
            )

            # Show trusted roles if configured
            if trusted_role_ids_str:
                trusted_role_mentions = []
                for role_id in trusted_role_ids_str.split(","):
                    role = interaction.guild.get_role(int(role_id))
                    if role:
                        trusted_role_mentions.append(role.mention)

                if trusted_role_mentions:
                    embed.add_field(
                        name="🔒 Trusted Roles",
                        value="Users with these roles are automatically trusted:\n"
                        + "\n".join(f"• {r}" for r in trusted_role_mentions),
                        inline=False,
                    )

            embed.set_footer(
                text=f"Configured by {interaction.user} | Use /impersonation-config to update"
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.info(
                f"Impersonation detection configured for guild {interaction.guild.id} by {interaction.user.id}"
            )

        except Exception as e:
            logger.error(f"Error in impersonation-setup: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-config",
        description="View or update impersonation detection settings",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        enabled="Enable or disable detection",
        moderation_channel="Channel for alerts",
        min_score="Minimum score threshold (0-100)",
        auto_quarantine="Enable/disable auto-quarantine",
        quarantine_role="Quarantine role",
        auto_dm="Enable/disable auto-DM",
        trusted_roles="Trusted roles (comma-separated mentions) - users with these roles are skipped",
    )
    async def impersonation_config(
        interaction: discord.Interaction,
        enabled: bool | None = None,
        moderation_channel: discord.TextChannel | None = None,
        min_score: int | None = None,
        auto_quarantine: bool | None = None,
        quarantine_role: discord.Role | None = None,
        auto_dm: bool | None = None,
        trusted_roles: str | None = None,
    ):
        """View or update impersonation detection configuration."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session, interaction.guild.id
                )

                if not guild_config:
                    await interaction.followup.send(
                        "❌ Server not configured. Please run `/setup` first.",
                        ephemeral=True,
                    )
                    return

                # If no parameters provided, show current config
                if all(
                    v is None
                    for v in [
                        enabled,
                        moderation_channel,
                        min_score,
                        auto_quarantine,
                        quarantine_role,
                        auto_dm,
                        trusted_roles,
                    ]
                ):
                    embed = discord.Embed(
                        title="⚙️ Impersonation Detection Configuration",
                        description=f"Current settings for **{interaction.guild.name}**",
                        color=discord.Color.blue(),
                    )

                    embed.add_field(
                        name="Status",
                        value=(
                            "✅ Enabled"
                            if guild_config.impersonation_detection_enabled
                            else "❌ Disabled"
                        ),
                        inline=True,
                    )

                    mod_channel = (
                        interaction.guild.get_channel(
                            guild_config.impersonation_moderation_channel_id
                        )
                        if guild_config.impersonation_moderation_channel_id
                        else None
                    )
                    embed.add_field(
                        name="Moderation Channel",
                        value=mod_channel.mention if mod_channel else "Not set",
                        inline=True,
                    )

                    embed.add_field(
                        name="Min Score",
                        value=f"{guild_config.impersonation_min_score_threshold}/100",
                        inline=True,
                    )

                    strategies = []
                    if guild_config.impersonation_alert_only_enabled:
                        strategies.append("• Alert Only")
                    if guild_config.impersonation_auto_quarantine_enabled:
                        quar_role = (
                            interaction.guild.get_role(
                                guild_config.impersonation_quarantine_role_id
                            )
                            if guild_config.impersonation_quarantine_role_id
                            else None
                        )
                        strategies.append(
                            f"• Auto-Quarantine ({quar_role.mention if quar_role else 'N/A'})"
                        )
                    if guild_config.impersonation_auto_dm_enabled:
                        strategies.append("• Auto-DM Users")

                    embed.add_field(
                        name="Active Strategies",
                        value="\n".join(strategies) if strategies else "None",
                        inline=False,
                    )

                    # Show trusted roles if configured
                    if guild_config.impersonation_trusted_role_ids:
                        trusted_role_mentions = []
                        for (
                            role_id
                        ) in guild_config.impersonation_trusted_role_ids.split(","):
                            if role_id.strip():
                                role = interaction.guild.get_role(int(role_id))
                                if role:
                                    trusted_role_mentions.append(role.mention)

                        if trusted_role_mentions:
                            embed.add_field(
                                name="🔒 Trusted Roles",
                                value="Users with these roles are automatically trusted:\n"
                                + "\n".join(f"• {r}" for r in trusted_role_mentions),
                                inline=False,
                            )
                    else:
                        embed.add_field(
                            name="🔒 Trusted Roles",
                            value="None configured (only our verified users are trusted)",
                            inline=False,
                        )

                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Update settings
                updates: dict[str, int | str | bool | None] = {}
                if enabled is not None:
                    updates["impersonation_detection_enabled"] = enabled
                if moderation_channel is not None:
                    updates["impersonation_moderation_channel_id"] = (
                        moderation_channel.id
                    )
                if min_score is not None:
                    if not 0 <= min_score <= 100:
                        await interaction.followup.send(
                            "❌ Minimum score must be between 0 and 100.",
                            ephemeral=True,
                        )
                        return
                    updates["impersonation_min_score_threshold"] = min_score
                if auto_quarantine is not None:
                    updates["impersonation_auto_quarantine_enabled"] = auto_quarantine
                    if auto_quarantine and not quarantine_role:
                        # Check if role already set
                        if not guild_config.impersonation_quarantine_role_id:
                            await interaction.followup.send(
                                "❌ Quarantine role required when enabling auto-quarantine.",
                                ephemeral=True,
                            )
                            return
                if quarantine_role is not None:
                    updates["impersonation_quarantine_role_id"] = quarantine_role.id
                if auto_dm is not None:
                    updates["impersonation_auto_dm_enabled"] = auto_dm
                if trusted_roles is not None:
                    # Parse trusted role IDs
                    import re

                    role_ids = re.findall(r"<@&(\d+)>|(\d+)", trusted_roles)
                    role_ids = [r[0] or r[1] for r in role_ids]
                    updates["impersonation_trusted_role_ids"] = (
                        ",".join(role_ids) if role_ids else None
                    )

                # Update alert_only based on other strategies
                if auto_quarantine is not None or auto_dm is not None:
                    updates["impersonation_alert_only_enabled"] = not (
                        updates.get(
                            "impersonation_auto_quarantine_enabled",
                            guild_config.impersonation_auto_quarantine_enabled,
                        )
                        or updates.get(
                            "impersonation_auto_dm_enabled",
                            guild_config.impersonation_auto_dm_enabled,
                        )
                    )

                await GuildConfigRepository.update(
                    db_session, interaction.guild.id, **updates
                )
                await db_session.commit()

            await interaction.followup.send(
                "✅ Configuration updated successfully!", ephemeral=True
            )

            logger.info(
                f"Impersonation config updated for guild {interaction.guild.id} by {interaction.user.id}"
            )

        except Exception as e:
            logger.error(f"Error in impersonation-config: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-review",
        description="List detected suspicious users awaiting review",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        status="Filter by status (pending, all, reviewed)",
        limit="Maximum number of results (1-100, default: 25)",
    )
    async def impersonation_review(
        interaction: discord.Interaction,
        status: str = "pending",
        limit: int = 25,
    ):
        """List impersonation detections for review."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            if not 1 <= limit <= 100:
                await interaction.followup.send(
                    "❌ Limit must be between 1 and 100.", ephemeral=True
                )
                return

            async with get_db_session() as db_session:
                if status == "pending":
                    detections = (
                        await ImpersonationDetectionRepository.get_pending_by_guild(
                            db_session, interaction.guild.id, limit=limit
                        )
                    )
                elif status == "all":
                    detections = (
                        await ImpersonationDetectionRepository.get_by_guild_and_status(
                            db_session,
                            interaction.guild.id,
                            status="pending",
                            limit=limit,
                        )
                    )
                    # Get all statuses
                    all_detections: list[ImpersonationDetection] = []
                    for stat in [
                        "pending",
                        "reviewed_safe",
                        "actioned_ban",
                        "actioned_kick",
                        "actioned_warn",
                        "false_positive",
                    ]:
                        dets = await ImpersonationDetectionRepository.get_by_guild_and_status(
                            db_session, interaction.guild.id, status=stat, limit=limit
                        )
                        all_detections.extend(dets)
                    detections = sorted(
                        all_detections, key=lambda d: d.detected_at, reverse=True
                    )[:limit]
                else:
                    # Specific status
                    detections = (
                        await ImpersonationDetectionRepository.get_by_guild_and_status(
                            db_session, interaction.guild.id, status=status, limit=limit
                        )
                    )

            if not detections:
                await interaction.followup.send(
                    f"✅ No detections found with status '{status}'.", ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=f"🔍 Impersonation Detections ({status.title()})",
                description=f"Showing {len(detections)} detection(s)",
                color=discord.Color.blue(),
            )

            for detection in detections[:10]:  # Show max 10 in embed
                risk_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                }
                emoji = risk_emoji.get(detection.risk_level, "⚪")

                value = (
                    f"**User:** <@{detection.discord_user_id}> (`{detection.discord_username}`)\n"
                    f"**Suspected:** {detection.suspected_streamer_username}\n"
                    f"**Score:** {emoji} {detection.total_score}/100 ({detection.risk_level})\n"
                    f"**Status:** {detection.status}\n"
                    f"**Detected:** <t:{int(detection.detected_at.timestamp())}:R>"
                )

                embed.add_field(
                    name=f"Detection #{detection.id}", value=value, inline=False
                )

            if len(detections) > 10:
                embed.set_footer(
                    text=f"Showing 10 of {len(detections)} results. Use /impersonation-details to view specific detections."
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in impersonation-review: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-details",
        description="View detailed information about a detection",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The user to view detection details for")
    async def impersonation_details(
        interaction: discord.Interaction, user: discord.Member
    ):
        """View detailed detection information for a specific user."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            async with get_db_session() as db_session:
                detection = (
                    await ImpersonationDetectionRepository.get_by_user_and_guild(
                        db_session, user.id, interaction.guild.id
                    )
                )

            if not detection:
                await interaction.followup.send(
                    f"✅ No detection found for {user.mention}.", ephemeral=True
                )
                return

            # Create detailed embed (reuse from moderation service)
            embed = await impersonation_moderation_service.create_alert_embed(
                detection, user
            )

            # Add review information if reviewed
            if detection.reviewed_by_user_id and detection.reviewed_at:
                review_info = (
                    f"**Reviewed By:** <@{detection.reviewed_by_user_id}>\n"
                    f"**Action:** {detection.moderator_action or 'None'}\n"
                    f"**Status:** {detection.status}\n"
                    f"**Reviewed:** <t:{int(detection.reviewed_at.timestamp())}:R>"
                )
                if detection.moderator_notes:
                    review_info += f"\n**Notes:** {detection.moderator_notes}"

                embed.add_field(
                    name="📋 Review Information", value=review_info, inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in impersonation-details: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-whitelist",
        description="Manage impersonation detection whitelist",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        action="Action to perform (add, remove, list)",
        user="User to add/remove from whitelist",
        reason="Reason for whitelisting",
    )
    async def impersonation_whitelist(
        interaction: discord.Interaction,
        action: str,
        user: discord.Member | None = None,
        reason: str | None = None,
    ):
        """Manage the impersonation detection whitelist."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            async with get_db_session() as db_session:
                if action == "add":
                    if not user:
                        await interaction.followup.send(
                            "❌ User parameter is required for 'add' action.",
                            ephemeral=True,
                        )
                        return

                    # Add to whitelist
                    await ImpersonationWhitelistRepository.create(
                        db_session,
                        guild_id=interaction.guild.id,
                        discord_user_id=user.id,
                        discord_username=str(user),
                        added_by_user_id=interaction.user.id,
                        added_by_username=str(interaction.user),
                        reason=reason or "No reason provided",
                    )
                    await db_session.commit()

                    await interaction.followup.send(
                        f"✅ Added {user.mention} to whitelist. This user will not be flagged for impersonation.",
                        ephemeral=True,
                    )

                elif action == "remove":
                    if not user:
                        await interaction.followup.send(
                            "❌ User parameter is required for 'remove' action.",
                            ephemeral=True,
                        )
                        return

                    deleted = await ImpersonationWhitelistRepository.delete(
                        db_session, user.id, interaction.guild.id
                    )
                    await db_session.commit()

                    if deleted:
                        await interaction.followup.send(
                            f"✅ Removed {user.mention} from whitelist.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(
                            f"❌ {user.mention} was not on the whitelist.",
                            ephemeral=True,
                        )

                elif action == "list":
                    whitelist = await ImpersonationWhitelistRepository.get_by_guild(
                        db_session, interaction.guild.id
                    )

                    if not whitelist:
                        await interaction.followup.send(
                            "✅ Whitelist is empty.", ephemeral=True
                        )
                        return

                    embed = discord.Embed(
                        title="📋 Impersonation Whitelist",
                        description=f"{len(whitelist)} whitelisted user(s)",
                        color=discord.Color.blue(),
                    )

                    for entry in whitelist[:25]:  # Max 25 fields
                        value = (
                            f"**User:** <@{entry.discord_user_id}>\n"
                            f"**Added By:** {entry.added_by_username}\n"
                            f"**Reason:** {entry.reason or 'None'}\n"
                            f"**Added:** <t:{int(entry.created_at.timestamp())}:R>"
                        )
                        embed.add_field(
                            name=f"ID: {entry.id}", value=value, inline=False
                        )

                    if len(whitelist) > 25:
                        embed.set_footer(text=f"Showing 25 of {len(whitelist)} entries")

                    await interaction.followup.send(embed=embed, ephemeral=True)

                else:
                    await interaction.followup.send(
                        f"❌ Unknown action '{action}'. Valid actions: add, remove, list",
                        ephemeral=True,
                    )

        except Exception as e:
            logger.error(f"Error in impersonation-whitelist: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-stats",
        description="View impersonation detection statistics",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(period="Time period (24h, 7d, 30d, all)", default="7d")
    async def impersonation_stats(interaction: discord.Interaction, period: str = "7d"):
        """View impersonation detection statistics."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            # Parse period
            period_map = {"24h": 1, "7d": 7, "30d": 30, "all": 9999}
            days = period_map.get(period)
            if days is None:
                await interaction.followup.send(
                    f"❌ Invalid period '{period}'. Valid: 24h, 7d, 30d, all",
                    ephemeral=True,
                )
                return

            async with get_db_session() as db_session:
                stats = await ImpersonationDetectionRepository.get_stats(
                    db_session, interaction.guild.id, days=days
                )

            embed = discord.Embed(
                title=f"📊 Impersonation Detection Statistics ({period})",
                description=f"Statistics for **{interaction.guild.name}**",
                color=discord.Color.blue(),
            )

            embed.add_field(
                name="Total Detections",
                value=f"**{stats['total_detections']}**",
                inline=True,
            )
            embed.add_field(
                name="Pending Reviews",
                value=f"**{stats['pending_reviews']}**",
                inline=True,
            )
            embed.add_field(
                name="Actions Taken",
                value=f"**{stats['actions_taken']}**",
                inline=True,
            )

            # Calculate rates
            if stats["total_detections"] > 0:
                action_rate = (stats["actions_taken"] / stats["total_detections"]) * 100
                embed.add_field(
                    name="Action Rate",
                    value=f"{action_rate:.1f}%",
                    inline=True,
                )

            embed.set_footer(
                text=f"Period: {period} | Use /impersonation-review to see details"
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in impersonation-stats: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @bot.tree.command(
        name="impersonation-cache-refresh",
        description="Manually refresh streamer cache from Twitch API",
    )
    @app_commands.default_permissions(administrator=True)
    async def impersonation_cache_refresh(interaction: discord.Interaction):
        """Manually trigger streamer cache refresh."""
        await interaction.response.defer(ephemeral=True)

        try:
            async with get_db_session() as db_session:
                # Get all cache entries
                cache_entries = await StreamerCacheRepository.get_all_cached(db_session)

            if not cache_entries:
                await interaction.followup.send(
                    "✅ Cache is empty. No entries to refresh.", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"🔄 Refreshing {len(cache_entries)} streamer cache entries...\nThis may take a few minutes.",
                ephemeral=True,
            )

            # Refresh entries
            refreshed = 0
            failed = 0

            for entry in cache_entries[:100]:  # Limit to 100 to avoid timeout
                async with get_db_session() as db_session:
                    success = (
                        await impersonation_detection_service.refresh_streamer_cache(
                            db_session, entry.twitch_user_id
                        )
                    )
                if success:
                    refreshed += 1
                else:
                    failed += 1

            # Send summary
            summary_embed = discord.Embed(
                title="✅ Cache Refresh Complete",
                description="Refreshed cache entries from Twitch API",
                color=discord.Color.green(),
            )
            summary_embed.add_field(name="Refreshed", value=f"{refreshed}", inline=True)
            summary_embed.add_field(name="Failed", value=f"{failed}", inline=True)

            await interaction.followup.send(embed=summary_embed, ephemeral=True)

            logger.info(
                f"Manual cache refresh completed: {refreshed} refreshed, {failed} failed"
            )

        except Exception as e:
            logger.error(f"Error in impersonation-cache-refresh: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    logger.info("Impersonation detection commands registered")
