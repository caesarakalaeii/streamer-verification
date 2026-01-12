"""Discord UI interaction handlers (buttons, modals) for impersonation detection."""

import logging

import discord

from src.database.connection import get_db_session
from src.database.repositories import (
    GuildConfigRepository,
    ImpersonationDetectionRepository,
)
from src.services.impersonation_moderation_service import (
    impersonation_moderation_service,
)

logger = logging.getLogger(__name__)


class ActionReasonModal(discord.ui.Modal):
    """Modal for collecting reason and notes for moderation actions."""

    def __init__(self, action: str, detection_id: int):
        """
        Initialize modal.

        Args:
            action: Action being taken (ban, kick, warn, etc.)
            detection_id: ID of detection being actioned
        """
        super().__init__(title=f"{action.capitalize()} User")
        self.action = action
        self.detection_id = detection_id

    reason: discord.ui.TextInput = discord.ui.TextInput(
        label="Reason",
        placeholder="Reason for this action (will be shown to user if applicable)",
        required=False,
        max_length=200,
        style=discord.TextStyle.short,
    )

    notes: discord.ui.TextInput = discord.ui.TextInput(
        label="Private Notes",
        placeholder="Internal notes for moderators (not shown to user)",
        required=False,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure user is a Member (not User)
            if not isinstance(interaction.user, discord.Member):
                await interaction.followup.send(
                    "❌ This command can only be used in a server.", ephemeral=True
                )
                return

            # Get detection from database
            async with get_db_session() as db_session:
                detection = await ImpersonationDetectionRepository.get_by_id(
                    db_session, self.detection_id
                )

                if not detection:
                    await interaction.followup.send(
                        "❌ Detection not found.", ephemeral=True
                    )
                    return

                # Execute action
                success, message = (
                    await impersonation_moderation_service.execute_action(
                        db_session,
                        detection,
                        self.action,
                        interaction.user,
                        reason=self.reason.value or None,
                        notes=self.notes.value or None,
                    )
                )

            if success:
                # Update original message to show action taken
                if interaction.message:
                    try:
                        # Get current embed
                        embed = (
                            interaction.message.embeds[0]
                            if interaction.message.embeds
                            else None
                        )
                        if embed:
                            # Update embed to show action taken
                            embed.color = discord.Color.green()
                            embed.title = "✅ Action Taken"
                            embed.set_footer(
                                text=f"Action: {self.action.upper()} by {interaction.user} | Detection ID: {self.detection_id}"
                            )

                            # Remove buttons
                            await interaction.message.edit(embed=embed, view=None)
                    except Exception as e:
                        logger.error(f"Failed to update alert message: {e}")

                await interaction.followup.send(f"✅ {message}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed: {message}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in modal submission: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )


class ImpersonationAlertView(discord.ui.View):
    """
    Persistent view for impersonation alert buttons.

    This view survives bot restarts (K8s pod restarts) by:
    1. Having timeout=None (persistent)
    2. Encoding detection_id in button custom_ids
    3. Fetching detection from database on interaction
    """

    def __init__(self, detection_id: int | None = None):
        """
        Initialize view.

        Args:
            detection_id: ID of detection (None when registering persistent view on startup)
        """
        # Persistent view - no timeout
        super().__init__(timeout=None)
        self.detection_id = detection_id

        # If detection_id provided, set it in button custom_ids
        if detection_id:
            self.ban_button.custom_id = f"imp_ban_{detection_id}"
            self.kick_button.custom_id = f"imp_kick_{detection_id}"
            self.warn_button.custom_id = f"imp_warn_{detection_id}"
            self.mark_safe_button.custom_id = f"imp_safe_{detection_id}"
            self.false_positive_button.custom_id = f"imp_false_{detection_id}"

    @discord.ui.button(
        label="Ban",
        style=discord.ButtonStyle.danger,
        emoji="🔨",
        custom_id="imp_ban",
    )
    async def ban_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle ban button click."""
        if not button.custom_id:
            await interaction.response.send_message("❌ Invalid button", ephemeral=True)
            return

        detection_id = self._parse_detection_id(button.custom_id)
        if not detection_id:
            await interaction.response.send_message(
                "❌ Invalid detection ID", ephemeral=True
            )
            return

        # Check permissions (ensure user is Member)
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This action can only be used in a server.", ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ You don't have permission to ban members.", ephemeral=True
            )
            return

        # Show modal for reason/notes
        modal = ActionReasonModal(action="ban", detection_id=detection_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Kick",
        style=discord.ButtonStyle.danger,
        emoji="👢",
        custom_id="imp_kick",
    )
    async def kick_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle kick button click."""
        if not button.custom_id:
            await interaction.response.send_message("❌ Invalid button", ephemeral=True)
            return

        detection_id = self._parse_detection_id(button.custom_id)
        if not detection_id:
            await interaction.response.send_message(
                "❌ Invalid detection ID", ephemeral=True
            )
            return

        # Check permissions (ensure user is Member)
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This action can only be used in a server.", ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                "❌ You don't have permission to kick members.", ephemeral=True
            )
            return

        # Show modal for reason/notes
        modal = ActionReasonModal(action="kick", detection_id=detection_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Warn",
        style=discord.ButtonStyle.secondary,
        emoji="⚠️",
        custom_id="imp_warn",
    )
    async def warn_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle warn button click."""
        if not button.custom_id:
            await interaction.response.send_message("❌ Invalid button", ephemeral=True)
            return

        detection_id = self._parse_detection_id(button.custom_id)
        if not detection_id:
            await interaction.response.send_message(
                "❌ Invalid detection ID", ephemeral=True
            )
            return

        # Ensure user is Member and guild exists
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.response.send_message(
                "❌ This action can only be used in a server.", ephemeral=True
            )
            return

        # Check permissions (moderators can warn)
        async with get_db_session() as db_session:
            guild_config = await GuildConfigRepository.get_by_guild_id(
                db_session, interaction.guild.id
            )

        if guild_config:
            # Check if user is admin
            is_admin = (
                interaction.user.id == interaction.guild.owner_id
                or interaction.user.guild_permissions.administrator
            )

            # Check if user has admin role
            if not is_admin and guild_config.admin_role_ids:
                admin_role_ids = [
                    int(rid) for rid in guild_config.admin_role_ids.split(",")
                ]
                is_admin = any(
                    role.id in admin_role_ids for role in interaction.user.roles
                )

            if not is_admin:
                await interaction.response.send_message(
                    "❌ You don't have permission to warn users.", ephemeral=True
                )
                return

        # Show modal for reason/notes
        modal = ActionReasonModal(action="warn", detection_id=detection_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Mark Safe",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="imp_safe",
    )
    async def mark_safe_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle mark safe button click."""
        if not button.custom_id:
            await interaction.response.send_message("❌ Invalid button", ephemeral=True)
            return

        detection_id = self._parse_detection_id(button.custom_id)
        if not detection_id:
            await interaction.response.send_message(
                "❌ Invalid detection ID", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure user is Member
            if not isinstance(interaction.user, discord.Member):
                await interaction.followup.send(
                    "❌ This action can only be used in a server.", ephemeral=True
                )
                return

            # Get detection and execute action
            async with get_db_session() as db_session:
                detection = await ImpersonationDetectionRepository.get_by_id(
                    db_session, detection_id
                )

                if not detection:
                    await interaction.followup.send(
                        "❌ Detection not found.", ephemeral=True
                    )
                    return

                success, message = (
                    await impersonation_moderation_service.execute_action(
                        db_session,
                        detection,
                        "mark_safe",
                        interaction.user,
                        reason="Reviewed and determined safe",
                    )
                )

            if success:
                # Update message
                if interaction.message:
                    try:
                        embed = (
                            interaction.message.embeds[0]
                            if interaction.message.embeds
                            else None
                        )
                        if embed:
                            embed.color = discord.Color.green()
                            embed.title = "✅ Marked as Safe"
                            embed.set_footer(
                                text=f"Reviewed by {interaction.user} | Detection ID: {detection_id}"
                            )
                            await interaction.message.edit(embed=embed, view=None)
                    except Exception as e:
                        logger.error(f"Failed to update alert message: {e}")

                await interaction.followup.send(f"✅ {message}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed: {message}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error marking safe: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    @discord.ui.button(
        label="False Positive",
        style=discord.ButtonStyle.secondary,
        emoji="❌",
        custom_id="imp_false",
    )
    async def false_positive_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle false positive button click (adds to whitelist)."""
        if not button.custom_id:
            await interaction.response.send_message("❌ Invalid button", ephemeral=True)
            return

        detection_id = self._parse_detection_id(button.custom_id)
        if not detection_id:
            await interaction.response.send_message(
                "❌ Invalid detection ID", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Ensure user is Member
            if not isinstance(interaction.user, discord.Member):
                await interaction.followup.send(
                    "❌ This action can only be used in a server.", ephemeral=True
                )
                return

            # Get detection and execute action
            async with get_db_session() as db_session:
                detection = await ImpersonationDetectionRepository.get_by_id(
                    db_session, detection_id
                )

                if not detection:
                    await interaction.followup.send(
                        "❌ Detection not found.", ephemeral=True
                    )
                    return

                success, message = (
                    await impersonation_moderation_service.execute_action(
                        db_session,
                        detection,
                        "false_positive",
                        interaction.user,
                        reason="Marked as false positive - added to whitelist",
                    )
                )

            if success:
                # Update message
                if interaction.message:
                    try:
                        embed = (
                            interaction.message.embeds[0]
                            if interaction.message.embeds
                            else None
                        )
                        if embed:
                            embed.color = discord.Color.greyple()
                            embed.title = "❌ False Positive (Whitelisted)"
                            embed.set_footer(
                                text=f"Whitelisted by {interaction.user} | Detection ID: {detection_id}"
                            )
                            await interaction.message.edit(embed=embed, view=None)
                    except Exception as e:
                        logger.error(f"Failed to update alert message: {e}")

                await interaction.followup.send(
                    f"✅ {message}\nThis user will not be flagged again.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(f"❌ Failed: {message}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error marking false positive: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}", ephemeral=True
            )

    def _parse_detection_id(self, custom_id: str) -> int | None:
        """
        Parse detection ID from button custom_id.

        Args:
            custom_id: Button custom_id (format: "imp_action_123")

        Returns:
            Detection ID or None if invalid
        """
        try:
            parts = custom_id.split("_")
            if len(parts) >= 3:
                return int(parts[2])
            return None
        except (ValueError, IndexError):
            logger.error(f"Failed to parse detection ID from custom_id: {custom_id}")
            return None
