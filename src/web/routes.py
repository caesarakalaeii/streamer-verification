"""FastAPI routes for Discord Linked Roles OAuth flow."""

import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from src.database.connection import get_db_session
from src.database.repositories import VerificationAuditLogRepository
from src.services.discord_service import discord_service
from src.services.twitch_service import twitch_service
from src.services.verification_service import verification_service
from src.shared.constants import (
    AUDIT_ACTION_TWITCH_OAUTH_COMPLETED,
    SUCCESS_VERIFICATION_COMPLETE,
)
from src.shared.exceptions import (
    BotException,
    DiscordAccountAlreadyLinkedError,
    TwitchAccountAlreadyLinkedError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def render_html_page(title: str, message: str, is_error: bool = False) -> HTMLResponse:
    """Render a simple HTML page."""
    status_code = 400 if is_error else 200
    color = "#e74c3c" if is_error else "#27ae60"
    emoji = "❌" if is_error else "✅"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 500px;
                margin: 1rem;
            }}
            .emoji {{
                font-size: 4rem;
                margin-bottom: 1rem;
            }}
            h1 {{
                color: {color};
                margin-bottom: 1rem;
                font-size: 2rem;
            }}
            p {{
                color: #555;
                line-height: 1.6;
                margin-bottom: 1.5rem;
                font-size: 1.1rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="emoji">{emoji}</div>
            <h1>{title}</h1>
            <p>{message}</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=status_code)


def render_oauth_page(
    title: str, message: str, button_text: str, oauth_url: str
) -> HTMLResponse:
    """Render a page with OAuth button."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 500px;
                margin: 1rem;
            }}
            .logo {{
                font-size: 4rem;
                margin-bottom: 1rem;
            }}
            h1 {{
                color: #333;
                margin-bottom: 1rem;
                font-size: 2rem;
            }}
            p {{
                color: #555;
                line-height: 1.6;
                margin-bottom: 2rem;
                font-size: 1.1rem;
            }}
            .button {{
                display: inline-block;
                padding: 1rem 2rem;
                background: #6441A5;
                color: white;
                text-decoration: none;
                border-radius: 0.5rem;
                font-weight: bold;
                font-size: 1.1rem;
                transition: transform 0.2s, background 0.2s;
                border: none;
                cursor: pointer;
            }}
            .button:hover {{
                transform: translateY(-2px);
                background: #7D5BBE;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🎮</div>
            <h1>{title}</h1>
            <p>{message}</p>
            <a href="{oauth_url}" class="button">{button_text}</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/discord-verify")
async def discord_verify():
    """
    Discord Linked Roles verification initiation endpoint.

    This is the entry point when users click "Link" in Discord Connections.
    Redirects users to Discord OAuth authorization.
    """
    try:
        # Generate Discord OAuth URL
        oauth_url = discord_service.get_oauth_url()
        logger.info("Redirecting user to Discord OAuth for Linked Roles verification")
        return RedirectResponse(url=oauth_url)
    except Exception as e:
        logger.error(f"Error initiating Discord OAuth: {e}", exc_info=True)
        return render_html_page(
            "Error",
            "Failed to start verification. Please try again from your Discord profile settings.",
            is_error=True,
        )


@router.get("/linked-role", response_class=HTMLResponse)
async def linked_role_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Discord Linked Roles callback endpoint.

    Discord redirects here when user clicks "Link" in their profile.
    We exchange the code for a Discord token, then redirect to Twitch OAuth.

    Query params:
        code: Authorization code from Discord
        state: Optional state parameter from Discord
        error: Error from Discord OAuth (if any)
    """
    if error:
        logger.warning(f"Discord OAuth error: {error}")
        return render_html_page(
            "Authorization Cancelled",
            "You cancelled the Discord authorization. Please try again from your Discord profile settings.",
            is_error=True,
        )

    if not code:
        return render_html_page(
            "Invalid Callback",
            "Missing authorization code from Discord. Please try again from your Discord profile settings.",
            is_error=True,
        )

    try:
        # Exchange Discord code for access token
        discord_access_token = await discord_service.exchange_code_for_token(code)

        # Get Discord user info
        discord_user = await discord_service.get_user_info(discord_access_token)
        discord_user_id = int(discord_user["id"])

        # Store Discord token and user ID in session for Twitch callback
        # We'll use state parameter to pass this through Twitch OAuth
        session_data = f"{discord_user_id}:{discord_access_token}"

        # Generate Twitch OAuth URL with session data in state
        twitch_oauth_url = twitch_service.get_oauth_url(session_data)

        logger.info(
            f"Discord OAuth completed for user {discord_user_id}, redirecting to Twitch"
        )

        return render_oauth_page(
            title="Link Your Twitch Account",
            message="Now please authenticate with Twitch to complete the verification.",
            button_text="Connect with Twitch",
            oauth_url=twitch_oauth_url,
        )

    except BotException as e:
        logger.error(f"Discord callback error: {e}")
        return render_html_page("Error", e.user_message, is_error=True)
    except Exception as e:
        logger.error(f"Unexpected Discord callback error: {e}", exc_info=True)
        return render_html_page(
            "Error",
            "An unexpected error occurred. Please try again or contact support.",
            is_error=True,
        )


@router.get("/twitch-callback", response_class=HTMLResponse)
async def twitch_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Twitch OAuth callback endpoint.

    This completes the verification by:
    1. Creating the database verification record
    2. Pushing metadata to Discord (enables linked role)

    Query params:
        code: Authorization code from Twitch
        state: Session data from Discord OAuth (discord_user_id:access_token)
        error: Error from Twitch OAuth (if any)
    """
    if error:
        logger.warning(f"Twitch OAuth error: {error}")
        return render_html_page(
            "Authorization Cancelled",
            "You cancelled the Twitch authorization. Please start over from your Discord profile settings.",
            is_error=True,
        )

    if not code or not state:
        return render_html_page(
            "Invalid Callback",
            "Missing required parameters from Twitch. Please start over from your Discord profile settings.",
            is_error=True,
        )

    try:
        # Parse session data from state
        parts = state.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Invalid state parameter")

        discord_user_id = int(parts[0])
        discord_access_token = parts[1]

        # Exchange Twitch code for access token
        twitch_access_token = await twitch_service.exchange_code_for_token(code)

        # Fetch Twitch user info
        twitch_user = await twitch_service.get_user_info(twitch_access_token)
        twitch_user_id = twitch_user["id"]
        twitch_username = twitch_user["login"]
        twitch_display_name = twitch_user.get("display_name", twitch_username)

        # Get Discord username for audit logging
        discord_user = await discord_service.get_user_info(discord_access_token)
        discord_username = discord_user["username"]

        async with get_db_session() as db_session:
            # Create verification with 1-to-1 mapping enforcement
            await verification_service.verify_user(
                db_session,
                discord_user_id=discord_user_id,
                discord_username=discord_username,
                twitch_user_id=twitch_user_id,
                twitch_username=twitch_username,
                twitch_display_name=twitch_display_name,
            )

            # Audit log
            await VerificationAuditLogRepository.create(
                db_session,
                discord_user_id=discord_user_id,
                discord_username=discord_username,
                twitch_user_id=twitch_user_id,
                twitch_username=twitch_username,
                action=AUDIT_ACTION_TWITCH_OAUTH_COMPLETED,
            )

        # Push role connection metadata to Discord
        await discord_service.push_role_connection_metadata(
            discord_access_token,
            twitch_username,
        )

        logger.info(
            f"✅ Linked role verification completed: Discord {discord_user_id} → Twitch {twitch_username}"
        )

        # Immediately assign role and set nickname in all configured guilds
        try:
            from src.services.post_verification_service import post_verification_service

            async with get_db_session() as db_session:
                await post_verification_service.assign_role_and_nickname(
                    db_session,
                    discord_user_id=discord_user_id,
                    twitch_username=twitch_username,
                    twitch_display_name=twitch_display_name,
                )
        except Exception as e:
            # Log error but don't fail the verification flow
            logger.error(
                f"Failed to assign role/nickname immediately: {e}", exc_info=True
            )

        return render_html_page(
            "Verification Complete!",
            SUCCESS_VERIFICATION_COMPLETE.format(twitch_username=twitch_username),
        )

    except (DiscordAccountAlreadyLinkedError, TwitchAccountAlreadyLinkedError) as e:
        logger.error(f"Verification failed - account already linked: {e}")
        return render_html_page("Account Already Linked", e.user_message, is_error=True)
    except BotException as e:
        logger.error(f"Twitch callback error: {e}")
        return render_html_page("Error", e.user_message, is_error=True)
    except Exception as e:
        logger.error(f"Unexpected Twitch callback error: {e}", exc_info=True)
        return render_html_page(
            "Error",
            "An unexpected error occurred. Please try again or contact support.",
            is_error=True,
        )
