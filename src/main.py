"""Main application entry point."""

import asyncio
import logging
import signal
import sys

import uvicorn

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

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.web_host,
        port=config.web_port,
        log_level=config.log_level.lower(),
        access_log=config.debug_mode,
    )

    server = uvicorn.Server(uvicorn_config)

    try:
        logger.info(f"Starting web server on {config.web_host}:{config.web_port}...")
        await server.serve()
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
        bot_task = asyncio.create_task(run_bot())
        web_task = asyncio.create_task(run_web_server())

        # Wait for shutdown signal
        await shutdown_event.wait()

        logger.info("Shutdown signal received, stopping services...")

        # Cancel tasks
        bot_task.cancel()
        web_task.cancel()

        # Wait for tasks to complete cancellation
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
