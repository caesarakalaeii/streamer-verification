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
        description="Set up the bot for this server",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        verified_role="The role to automatically assign when users verify their Twitch account",
        admin_roles="Optional: Roles that can use admin commands (comma-separated mentions or IDs)",
    )
    async def setup(
        interaction: discord.Interaction,
        verified_role: discord.Role,
        admin_roles: str | None = None,
    ):
        """
        Setup command: Configure the bot for this guild (server owner only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure we're in a guild
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            guild = interaction.guild
            assert (
                guild.id is not None
            )  # For mypy - guild commands always have guild_id

            # Check if user is server owner or administrator
            if not (
                interaction.user.id == guild.owner_id
                or interaction.user.guild_permissions.administrator
            ):
                await interaction.followup.send(
                    "❌ Only the server owner or administrators can run this command.",
                    ephemeral=True,
                )
                return

            # Check if guild is already set up
            async with get_db_session() as db_session:
                existing_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    guild.id,
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

                    role_ids = re.findall(r"<@&(\d+)>|(\d+)", admin_roles)
                    role_ids = [r[0] or r[1] for r in role_ids]
                    admin_role_ids_str = ",".join(role_ids)

                # Create guild config
                await GuildConfigRepository.create(
                    db_session,
                    guild_id=guild.id,
                    guild_name=guild.name,
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
                    "**Tell your users to verify:**\n"
                    "Users can run `/verify` to get instructions, or they can:\n"
                    "1. Go to Discord Settings → Connections\n"
                    "2. Click **Link** on this app\n"
                    "3. Authenticate with Twitch\n"
                    "4. Their role and nickname will be automatically assigned!\n\n"
                    "**Admin commands:**\n"
                    "• `/config` - View or update server settings\n"
                    "• `/verify` - Show verification instructions\n"
                    "• `/unverify` - Remove user verification\n"
                    "• `/list-verified` - Show all verified users"
                ),
                inline=False,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(
                f"Guild {guild.id} ({guild.name}) configured by {interaction.user.id}"
            )

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
        description="Remove a user's Twitch verification",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="The user to unverify")
    async def unverify(interaction: discord.Interaction, user: discord.Member):
        """
        Unverify command: Remove a user's verification (admin only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure we're in a guild
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    interaction.guild.id,
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
                logger.info(
                    f"User {user.id} unverified by admin {interaction.user.id} in guild {interaction.guild_id}"
                )

                # Try to remove verified role from guild config
                try:
                    role = interaction.guild.get_role(guild_config.verified_role_id)
                    if role and role in user.roles:
                        await user.remove_roles(
                            role, reason=f"Unverified by {interaction.user}"
                        )
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
        description="List all verified users in this server",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_verified(interaction: discord.Interaction):
        """
        List verified users command: Show all verified users in this guild (admin only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure we're in a guild
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    interaction.guild.id,
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
                all_verifications = await verification_service.get_all_verifications(
                    db_session
                )

            # Filter to only members of this guild
            verifications = [
                v
                for v in all_verifications
                if interaction.guild.get_member(v.discord_user_id)
            ]

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

            # Build a text list instead of fields to handle hundreds of users
            user_list = []
            for verification in verifications:
                discord_user = interaction.guild.get_member(
                    verification.discord_user_id
                )
                discord_mention = (
                    discord_user.mention
                    if discord_user
                    else f"<@{verification.discord_user_id}>"
                )
                twitch_name = (
                    verification.twitch_display_name or verification.twitch_username
                )
                user_list.append(f"**{twitch_name}** → {discord_mention}")

            # Discord embed description limit is 4096 chars
            # If list is too long, paginate
            user_text = "\n".join(user_list)
            if len(user_text) > 4000:
                # Split into chunks
                chunks = []
                current_chunk = []
                current_length = 0

                for line in user_list:
                    line_length = len(line) + 1  # +1 for newline
                    if current_length + line_length > 4000:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_length = line_length
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                # Send first chunk
                embed.description = chunks[0]
                embed.set_footer(
                    text=f"Page 1 of {len(chunks)} • {len(verifications)} total users"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

                # Send remaining chunks
                for i, chunk in enumerate(chunks[1:], start=2):
                    page_embed = discord.Embed(
                        title="✅ Verified Users (continued)",
                        description=chunk,
                        color=discord.Color.green(),
                    )
                    page_embed.set_footer(
                        text=f"Page {i} of {len(chunks)} • {len(verifications)} total users"
                    )
                    await interaction.followup.send(embed=page_embed, ephemeral=True)
            else:
                embed.description = user_text
                await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(
                f"List verified command executed by admin {interaction.user.id}"
            )

        except Exception as e:
            logger.error(f"Error in list-verified command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching verified users. Please try again later.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="config",
        description="View or update server configuration",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        verified_role="Optional: Update the verified role",
        admin_roles="Optional: Update admin roles (comma-separated mentions or IDs)",
        nickname_enforcement="Optional: Enable or disable nickname enforcement",
    )
    async def config(
        interaction: discord.Interaction,
        verified_role: discord.Role | None = None,
        admin_roles: str | None = None,
        nickname_enforcement: bool | None = None,
    ):
        """
        Config command: View or update guild configuration (admin only).
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure we're in a guild
            if not interaction.guild or not isinstance(
                interaction.user, discord.Member
            ):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            guild = interaction.guild

            # Check if guild is configured
            async with get_db_session() as db_session:
                guild_config = await GuildConfigRepository.get_by_guild_id(
                    db_session,
                    guild.id,
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

            # If no parameters provided, show current config
            if (
                verified_role is None
                and admin_roles is None
                and nickname_enforcement is None
            ):
                embed = discord.Embed(
                    title="⚙️ Server Configuration",
                    description=f"Configuration for **{guild.name}**",
                    color=discord.Color.blue(),
                )

                embed.add_field(
                    name="Verified Role",
                    value=f"<@&{guild_config.verified_role_id}>",
                    inline=False,
                )

                embed.add_field(
                    name="Admin Roles",
                    value=guild_config.admin_role_ids
                    or "None (owner & administrators only)",
                    inline=False,
                )

                embed.add_field(
                    name="Nickname Enforcement",
                    value=(
                        "✅ Enabled"
                        if guild_config.nickname_enforcement_enabled
                        else "❌ Disabled"
                    ),
                    inline=False,
                )

                embed.add_field(
                    name="Setup Info",
                    value=f"Configured by: <@{guild_config.setup_by_user_id}>\n"
                    f"Setup at: <t:{int(guild_config.created_at.timestamp())}:F>",
                    inline=False,
                )

                embed.set_footer(text="Use /config with parameters to update settings")

                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Update configuration
            async with get_db_session() as db_session:
                # Parse admin role IDs if provided
                from typing import Any

                update_kwargs: dict[str, Any] = {}

                if verified_role is not None:
                    update_kwargs["verified_role_id"] = verified_role.id

                if admin_roles is not None:
                    import re

                    role_ids = re.findall(r"<@&(\d+)>|(\d+)", admin_roles)
                    role_ids = [r[0] or r[1] for r in role_ids]
                    admin_role_ids_value: str | None = (
                        ",".join(role_ids) if role_ids else None
                    )
                    update_kwargs["admin_role_ids"] = admin_role_ids_value

                if nickname_enforcement is not None:
                    update_kwargs["nickname_enforcement_enabled"] = nickname_enforcement

                # Update guild config
                await GuildConfigRepository.update(
                    db_session,
                    guild_id=guild.id,
                    **update_kwargs,
                )

            # Build response message
            changes = []
            if verified_role:
                changes.append(f"• Verified Role → {verified_role.mention}")
            if admin_roles is not None:
                changes.append(
                    f"• Admin Roles → {admin_roles or 'None (owner & administrators only)'}"
                )
            if nickname_enforcement is not None:
                changes.append(
                    f"• Nickname Enforcement → {'✅ Enabled' if nickname_enforcement else '❌ Disabled'}"
                )

            if not changes:
                await interaction.followup.send(
                    "⚠️ No changes were made. Provide at least one parameter to update.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="✅ Configuration Updated",
                description="The following settings have been updated:",
                color=discord.Color.green(),
            )

            embed.add_field(
                name="Changes",
                value="\n".join(changes),
                inline=False,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(
                f"Guild {guild.id} ({guild.name}) configuration updated by {interaction.user.id}: {changes}"
            )

        except Exception as e:
            logger.error(f"Error in config command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while updating configuration. Please try again later.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="verify",
        description="Get instructions on how to verify your Twitch account",
    )
    async def verify(interaction: discord.Interaction):
        """
        Verify command: Guide users through the verification process.
        """
        try:
            embed = discord.Embed(
                title="🎮 Verify Your Twitch Account",
                description="Follow these steps to link your Twitch account and get verified:",
                color=discord.Color.purple(),
            )

            embed.add_field(
                name="Step 1: Open Discord Settings",
                value="Click the ⚙️ (Settings) icon at the bottom left of Discord",
                inline=False,
            )

            embed.add_field(
                name="Step 2: Go to Connections",
                value="Find **Connections** in the left sidebar under 'User Settings'",
                inline=False,
            )

            bot_name = (
                interaction.client.user.name if interaction.client.user else "this app"
            )
            embed.add_field(
                name="Step 3: Find This App",
                value=f"Look for **{bot_name}** in the list of available connections",
                inline=False,
            )

            embed.add_field(
                name="Step 4: Click 'Link'",
                value="Click the **Link** button next to this app",
                inline=False,
            )

            embed.add_field(
                name="Step 5: Authenticate with Twitch",
                value="You'll be redirected to authenticate with Twitch. Sign in and authorize the connection.",
                inline=False,
            )

            embed.add_field(
                name="✅ That's it!",
                value="Once completed, your verified role and nickname will be automatically assigned!",
                inline=False,
            )

            embed.set_footer(
                text="Your Twitch username will become your nickname in this server"
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Verify command executed by user {interaction.user.id}")

        except Exception as e:
            logger.error(f"Error in verify command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred. Please try again later.",
                ephemeral=True,
            )


async def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions based on guild config."""
    # Ensure we're in a guild with a member
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False

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
            interaction.guild.id,
        )

        if not guild_config or not guild_config.admin_role_ids:
            return False

        # Parse admin role IDs from config
        admin_role_ids = [
            int(rid.strip())
            for rid in guild_config.admin_role_ids.split(",")
            if rid.strip()
        ]
        user_role_ids = [role.id for role in interaction.user.roles]

        return any(role_id in admin_role_ids for role_id in user_role_ids)
