"""FastAPI web application for OAuth callbacks."""

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.config import config

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Discord-Twitch Verification Bot",
        description="Dual OAuth verification system for Discord and Twitch",
        version="1.0.0",
        docs_url="/docs" if config.debug_mode else None,
        redoc_url="/redoc" if config.debug_mode else None,
    )

    # Import and include routers
    from src.web.routes import router
    app.include_router(router)

    @app.get("/health", response_class=HTMLResponse)
    async def health_check():
        """Health check endpoint."""
        return HTMLResponse(content="OK", status_code=200)

    logger.info("FastAPI application created")
    return app
