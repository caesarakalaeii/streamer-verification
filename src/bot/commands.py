"""Discord bot slash command handlers."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.database.connection import get_db_session
from src.database.repositories import GuildConfigRepository
from src.services.verification_service import verification_service
from src.shared.exceptions import RecordAlreadyExistsError

logger = logging.getLogger(__name__)


def setup_commands(bot: commands.Bot) -> None:
    """Register slash commands."""

    @bot.tree.command(
        name="setup",
        description="[Owner] Set up the bot for this server",
    )
    @app_commands.describe(
        verified_role="The role to assign to verified users",
        admin_roles="Optional: Roles that can use admin commands (comma-separated mentions or IDs)"
    )
    async def setup(
        interaction: discord.Interaction,
        verified_role: discord.Role,
        admin_roles: str = None,
    ):
        """
        Setup command: Configure the bot for this guild (server owner only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if user is server owner or administrator
            if not (interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator):
                await interaction.followup.send(
                    "❌ Only the server owner or administrators can run this command.",
                    ephemeral=True,
                )
                return

            # Check if guild is already set up
            async with get_db_session() as db_session:
                existing_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    interaction.guild_id,
                )

                if existing_config:
                    await interaction.followup.send(
                        f"⚠️ This server is already configured!\n\n"
                        f"**Current Settings:**\n"
                        f"• Verified Role: <@&{existing_config.verified_role_id}>\n"
                        f"• Admin Roles: {existing_config.admin_role_ids or 'None (owner only)'}\n"
                        f"• Nickname Enforcement: {'Enabled' if existing_config.nickname_enforcement_enabled else 'Disabled'}\n\n"
                        f"Use `/config` to update settings.",
                        ephemeral=True,
                    )
                    return

                # Parse admin role IDs
                admin_role_ids_str = None
                if admin_roles:
                    # Extract role IDs from mentions or raw IDs
                    import re
                    role_ids = re.findall(r'<@&(\d+)>|(\d+)', admin_roles)
                    role_ids = [r[0] or r[1] for r in role_ids]
                    admin_role_ids_str = ",".join(role_ids)

                # Create guild config
                await GuildConfigRepository.create(
                    db_session,
                    guild_id=interaction.guild_id,
                    guild_name=interaction.guild.name,
                    verified_role_id=verified_role.id,
                    setup_by_user_id=interaction.user.id,
                    setup_by_username=str(interaction.user),
                    admin_role_ids=admin_role_ids_str,
                )

            # Success message
            embed = discord.Embed(
                title="✅ Bot Setup Complete!",
                description="Your server is now configured for Twitch verification.",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Verified Role",
                value=verified_role.mention,
                inline=False,
            )
            embed.add_field(
                name="Admin Roles",
                value=admin_roles or "Server owner & administrators only",
                inline=False,
            )
            embed.add_field(
                name="Next Steps",
                value=(
                    "1. **Create a Discord role** with a Linked Role requirement:\n"
                    "   • Edit your role → **Links** tab\n"
                    "   • Add requirement: This app → **Verified on Twitch** = ✅\n\n"
                    "2. **Tell your users** to verify:\n"
                    "   • Go to Discord Settings → Connections\n"
                    "   • Click **Link** on this app\n"
                    "   • Authenticate with Twitch\n\n"
                    "3. **Use admin commands**:\n"
                    "   • `/config` - View or update settings\n"
                    "   • `/unverify` - Remove user verification\n"
                    "   • `/list-verified` - Show all verified users"
                ),
                inline=False,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Guild {interaction.guild_id} ({interaction.guild.name}) configured by {interaction.user.id}")

        except RecordAlreadyExistsError as e:
            await interaction.followup.send(f"❌ {e.user_message}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in setup command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred during setup. Please try again later.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="unverify",
        description="[Admin] Remove a user's Twitch verification",
    )
    @app_commands.describe(user="The user to unverify")
    async def unverify(interaction: discord.Interaction, user: discord.Member):
        """
        Unverify command: Remove a user's verification (admin only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    interaction.guild_id,
                )

            if not guild_config:
                await interaction.followup.send(
                    "❌ This server hasn't been set up yet. Run `/setup` first.",
                    ephemeral=True,
                )
                return

            # Check if user is admin
            if not await is_admin(interaction):
                await interaction.followup.send(
                    "❌ You don't have permission to use this command.",
                    ephemeral=True,
                )
                return

            # Unverify user
            async with get_db_session() as db_session:
                deleted = await verification_service.unverify_user(
                    db_session,
                    user.id,
                    admin_username=str(interaction.user),
                )

            if deleted:
                await interaction.followup.send(
                    f"✅ Successfully unverified {user.mention}",
                    ephemeral=True,
                )
                logger.info(f"User {user.id} unverified by admin {interaction.user.id} in guild {interaction.guild_id}")

                # Try to remove verified role from guild config
                try:
                    role = interaction.guild.get_role(guild_config.verified_role_id)
                    if role and role in user.roles:
                        await user.remove_roles(role, reason=f"Unverified by {interaction.user}")
                except discord.Forbidden:
                    logger.warning(f"No permission to remove role from user {user.id}")
                except Exception as e:
                    logger.error(f"Error removing role from user {user.id}: {e}")
            else:
                await interaction.followup.send(
                    f"❌ {user.mention} is not verified.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error in unverify command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while unverifying the user. Please try again later.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="list-verified",
        description="[Admin] List all verified users in this server",
    )
    async def list_verified(interaction: discord.Interaction):
        """
        List verified users command: Show all verified users in this guild (admin only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    interaction.guild_id,
                )

            if not guild_config:
                await interaction.followup.send(
                    "❌ This server hasn't been set up yet. Run `/setup` first.",
                    ephemeral=True,
                )
                return

            # Check if user is admin
            if not await is_admin(interaction):
                await interaction.followup.send(
                    "❌ You don't have permission to use this command.",
                    ephemeral=True,
                )
                return

            # Get all verifications for this guild only (filter by members in this guild)
            async with get_db_session() as db_session:
                all_verifications = await verification_service.get_all_verifications(db_session)

            # Filter to only members of this guild
            verifications = [v for v in all_verifications if interaction.guild.get_member(v.discord_user_id)]

            if not verifications:
                await interaction.followup.send(
                    "ℹ️ No verified users found.",
                    ephemeral=True,
                )
                return

            # Create embed with verified users
            embed = discord.Embed(
                title=f"✅ Verified Users ({len(verifications)})",
                color=discord.Color.green(),
            )

            # Add up to 25 fields (Discord limit)
            for verification in verifications[:25]:
                discord_user = interaction.guild.get_member(verification.discord_user_id)
                discord_mention = discord_user.mention if discord_user else f"<@{verification.discord_user_id}>"

                embed.add_field(
                    name=f"Twitch: {verification.twitch_username}",
                    value=f"Discord: {discord_mention}",
                    inline=False,
                )

            if len(verifications) > 25:
                embed.set_footer(text=f"Showing first 25 of {len(verifications)} verified users")

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"List verified command executed by admin {interaction.user.id}")

        except Exception as e:
            logger.error(f"Error in list-verified command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching verified users. Please try again later.",
                ephemeral=True,
            )


async def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions based on guild config."""
    # Server owner always has permission
    if interaction.user.id == interaction.guild.owner_id:
        return True

    # Check if user has administrator permission
    if interaction.user.guild_permissions.administrator:
        return True

    # Check guild config for admin roles
    async with get_db_session() as db_session:
        guild_config = await GuildConfigRepository.get_by_guild_id(
            db_session,
            interaction.guild_id,
        )

        if not guild_config or not guild_config.admin_role_ids:
            return False

        # Parse admin role IDs from config
        admin_role_ids = [int(rid.strip()) for rid in guild_config.admin_role_ids.split(",") if rid.strip()]
        user_role_ids = [role.id for role in interaction.user.roles]

        return any(role_id in admin_role_ids for role_id in user_role_ids)
