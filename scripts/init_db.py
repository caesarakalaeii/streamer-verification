#!/usr/bin/env python3
"""Database initialization script."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import config
from src.database.connection import init_db, close_db
from src.shared.logging import setup_logging


async def main() -> None:
    """Initialize the database."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting database initialization...")
    logger.info(f"Database: {config.database_name}")
    logger.info(f"Host: {config.database_host}:{config.database_port}")

    try:
        await init_db()
        logger.info("✅ Database initialization completed successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
