"""Database connection management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.config import config

logger = logging.getLogger(__name__)

# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            config.database_url,
            echo=config.debug_mode,
            pool_size=config.database_pool_size,
            max_overflow=config.database_max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            poolclass=(
                NullPool if config.debug_mode else None
            ),  # Disable pooling in debug mode
        )
        logger.info("Database engine created", extra={"database": config.database_name})
    return _engine


def get_session_factory() -> sessionmaker:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )  # type: ignore[call-overload]
        logger.info("Session factory created")
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session as an async context manager.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    factory = get_session_factory()
    session: AsyncSession = factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}", exc_info=True)
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database by running migrations."""
    import asyncpg

    # Connect to postgres database to create the target database if it doesn't exist
    try:
        conn = await asyncpg.connect(
            host=config.database_host,
            port=config.database_port,
            user=config.database_user,
            password=config.database_password,
            database="postgres",
        )

        # Check if database exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            config.database_name,
        )

        if not exists:
            await conn.execute(f'CREATE DATABASE "{config.database_name}"')
            logger.info(f"Created database: {config.database_name}")
        else:
            logger.info(f"Database already exists: {config.database_name}")

        await conn.close()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise

    # Run migrations
    try:
        conn = await asyncpg.connect(
            host=config.database_host,
            port=config.database_port,
            user=config.database_user,
            password=config.database_password,
            database=config.database_name,
        )

        migrations_dir = Path("src/database/migrations")
        migration_files = sorted(migrations_dir.glob("*.sql"))

        try:
            for migration_file in migration_files:
                logger.info("Applying migration %s", migration_file.name)
                migration_sql = migration_file.read_text()
                await conn.execute(migration_sql)

            logger.info("Database migrations completed successfully")
        except asyncpg.exceptions.InsufficientPrivilegeError as exc:
            logger.warning(
                "Skipping migrations because user '%s' lacks privileges: %s. "
                "Run scripts/init_db.py with a privileged account to apply pending migrations.",
                config.database_user,
                exc,
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}", exc_info=True)
        raise


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")
