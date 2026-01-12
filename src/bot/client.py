"""Discord bot client setup."""

import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


def create_bot() -> commands.Bot:
    """Create and configure the Discord bot."""
    intents = discord.Intents.default()
    intents.members = True  # Required for member events and nickname management
    intents.guilds = True
    intents.presences = (
        True  # Required for accessing user bios/about me (impersonation detection)
    )

    bot = commands.Bot(
        command_prefix="!",  # Prefix for text commands (not used for slash commands)
        intents=intents,
        help_command=None,  # Disable default help command
    )

    @bot.event
    async def on_ready():
        """Called when the bot is ready."""
        logger.info(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})")
        logger.info(f"Connected to {len(bot.guilds)} guilds")

        # List guilds
        for guild in bot.guilds:
            logger.info(
                f"  - {guild.name} (ID: {guild.id}, Members: {guild.member_count})"
            )

        # Register persistent views (for K8s restart support)
        from src.bot.interactions import ImpersonationAlertView

        bot.add_view(ImpersonationAlertView())
        logger.info("Registered persistent impersonation alert view")

        # Sync slash commands globally
        try:
            await bot.tree.sync()
            logger.info("Slash commands synced globally")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}", exc_info=True)

    @bot.event
    async def on_error(event: str, *args, **kwargs):
        """Global error handler."""
        logger.error(f"Bot error in event {event}", exc_info=True)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ):
        """Global error handler for slash commands."""
        logger.error(
            f"Slash command error in {interaction.command.name if interaction.command else 'unknown'}: {error}",
            exc_info=error,
        )

        # Try to send error message to user
        try:
            error_message = f"❌ An error occurred: {str(error)}"
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

    # Register cogs/commands
    from src.bot.commands import setup_commands
    from src.bot.commands_impersonation import setup_impersonation_commands
    from src.bot.events import setup_events
    from src.bot.tasks import setup_tasks

    setup_commands(bot)
    setup_impersonation_commands(bot)
    setup_events(bot)
    setup_tasks(bot)

    logger.info("Discord bot configured")
    return bot
