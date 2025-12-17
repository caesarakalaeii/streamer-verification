"""Main application entry point."""

import asyncio
import logging
import signal
import sys

from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig

from src.bot.client import create_bot
from src.config import config
from src.database.connection import close_db, init_db
from src.shared.logging import setup_logging
from src.web.app import create_app

logger = logging.getLogger(__name__)

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def run_bot():
    """Run the Discord bot."""
    bot = create_bot()

    # Set global bot instance for cross-module access
    from src.bot.bot_instance import set_bot_instance
    set_bot_instance(bot)

    try:
        logger.info("Starting Discord bot...")
        await bot.start(config.discord_bot_token)
    except Exception as e:
        logger.error(f"Discord bot error: {e}", exc_info=True)
        raise
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Discord bot stopped")


async def run_web_server():
    """Run the FastAPI web server."""
    app = create_app()

    hypercorn_config = HypercornConfig()
    hypercorn_config.bind = [f"{config.web_host}:{config.web_port}"]
    hypercorn_config.loglevel = config.log_level.lower()
    hypercorn_config.accesslog = "-" if config.debug_mode else None

    try:
        logger.info(f"Starting web server on {config.web_host}:{config.web_port}...")
        await serve(app, hypercorn_config, shutdown_trigger=shutdown_event.wait)
    except Exception as e:
        logger.error(f"Web server error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Web server stopped")


async def main():
    """Main application entry point."""
    # Set up logging
    setup_logging()
    logger.info("=" * 60)
    logger.info("Discord-Twitch Verification Bot Starting")
    logger.info("=" * 60)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")

        # Register Discord Linked Roles metadata
        logger.info("Registering Discord Linked Roles metadata...")
        from src.services.discord_service import discord_service
        await discord_service.register_metadata()
        logger.info("Discord metadata registered successfully")

        # Create tasks for bot and web server
        # Note: hypercorn's serve() uses shutdown_trigger, so web server will stop when shutdown_event is set
        bot_task = asyncio.create_task(run_bot())
        web_task = asyncio.create_task(run_web_server())

        # Wait for shutdown signal or either task to complete
        done, pending = await asyncio.wait(
            [bot_task, web_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        logger.info("Shutdown initiated, stopping services...")

        # Set shutdown event to stop web server gracefully
        shutdown_event.set()

        # Cancel remaining tasks
        for task in pending:
            task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(bot_task, web_task, return_exceptions=True)

    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Clean up database connections
        logger.info("Closing database connections...")
        await close_db()
        logger.info("=" * 60)
        logger.info("Discord-Twitch Verification Bot Stopped")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
