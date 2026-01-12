"""Global bot instance holder for cross-module access."""

from typing import Optional

from discord.ext import commands  # type: ignore[attr-defined]

# Global bot instance (set during startup)
_bot_instance: Optional[commands.Bot] = None  # type: ignore[valid-type]


def set_bot_instance(bot: commands.Bot) -> None:  # type: ignore[valid-type]
    """Set the global bot instance."""
    global _bot_instance
    _bot_instance = bot


def get_bot_instance() -> Optional[commands.Bot]:  # type: ignore[valid-type]
    """Get the global bot instance."""
    return _bot_instance
