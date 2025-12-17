"""Discord Linked Roles API client service."""

import logging
from typing import Any

import httpx

from src.config import config
from src.shared.constants import (
    DISCORD_API_BASE,
    DISCORD_OAUTH_AUTHORIZE,
    DISCORD_OAUTH_SCOPES,
    DISCORD_OAUTH_TOKEN,
    DISCORD_USERS_ME,
)
from src.shared.exceptions import DiscordAPIError

logger = logging.getLogger(__name__)


class DiscordService:
    """Service for Discord Linked Roles API interactions."""

    @staticmethod
    def get_oauth_url(state: str | None = None) -> str:
        """
        Generate Discord OAuth authorization URL for Linked Roles.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Full OAuth authorization URL
        """
        scopes = " ".join(DISCORD_OAUTH_SCOPES)
        params = {
            "client_id": config.discord_oauth_client_id,
            "redirect_uri": config.discord_oauth_redirect_uri,
            "response_type": "code",
            "scope": scopes,
        }

        if state:
            params["state"] = state

        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{DISCORD_OAUTH_AUTHORIZE}?{param_str}"
        logger.debug(f"Generated Discord OAuth URL for Linked Roles")
        return url

    @staticmethod
    async def register_metadata() -> None:
        """
        Register metadata schema for linked roles with Discord.

        This defines what metadata fields the app can set for users.
        Should be called once on application startup.
        """
        metadata_schema = [
            {
                "key": "verified_on_twitch",
                "name": "Verified on Twitch",
                "description": "User has linked their Twitch account",
                "type": 7,  # BOOLEAN_EQUAL
            }
        ]

        url = f"{DISCORD_API_BASE}/applications/{config.discord_oauth_client_id}/role-connections/metadata"
        headers = {
            "Authorization": f"Bot {config.discord_bot_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    url,
                    headers=headers,
                    json=metadata_schema,
                    timeout=10.0,
                )

                if response.status_code not in (200, 201):
                    error_data = response.json() if response.content else {}
                    logger.error(
                        f"Failed to register metadata: {response.status_code}, {error_data}"
                    )
                    raise DiscordAPIError(
                        f"Failed to register metadata: {response.status_code}",
                        "Failed to configure Discord integration.",
                    )

                logger.info("Successfully registered linked roles metadata schema")

        except httpx.RequestError as e:
            logger.error(f"Discord API request error: {e}")
            raise DiscordAPIError(
                f"Discord API request failed: {e}",
                "Failed to connect to Discord.",
            ) from e

    @staticmethod
    async def exchange_code_for_token(code: str) -> str:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Access token

        Raises:
            DiscordAPIError: Failed to exchange code
        """
        data = {
            "client_id": config.discord_oauth_client_id,
            "client_secret": config.discord_oauth_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.discord_oauth_redirect_uri,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DISCORD_OAUTH_TOKEN,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10.0,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    logger.error(
                        f"Discord token exchange failed: {response.status_code}, {error_data}"
                    )
                    raise DiscordAPIError(
                        f"Failed to exchange code for token: {response.status_code}",
                        "Failed to authenticate with Discord. Please try again.",
                    )

                token_data = response.json()
                access_token = token_data.get("access_token")

                if not access_token:
                    logger.error(f"No access token in Discord response: {token_data}")
                    raise DiscordAPIError(
                        "No access token in response",
                        "Failed to authenticate with Discord. Please try again.",
                    )

                logger.info("Successfully exchanged Discord code for access token")
                return str(access_token)

        except httpx.RequestError as e:
            logger.error(f"Discord API request error: {e}")
            raise DiscordAPIError(
                f"Discord API request failed: {e}",
                "Failed to connect to Discord. Please try again.",
            ) from e

    @staticmethod
    async def get_user_info(access_token: str) -> dict[str, Any]:
        """
        Fetch Discord user information using access token.

        Args:
            access_token: Discord access token

        Returns:
            User info dict with 'id', 'username', etc.

        Raises:
            DiscordAPIError: Failed to fetch user info
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    DISCORD_USERS_ME,
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    logger.error(
                        f"Discord user info fetch failed: {response.status_code}, {error_data}"
                    )
                    raise DiscordAPIError(
                        f"Failed to fetch user info: {response.status_code}",
                        "Failed to fetch your Discord information. Please try again.",
                    )

                user_data: dict[str, Any] = response.json()
                logger.info(
                    f"Fetched Discord user info: {user_data.get('id')} ({user_data.get('username')})"
                )
                return user_data

        except httpx.RequestError as e:
            logger.error(f"Discord API request error: {e}")
            raise DiscordAPIError(
                f"Discord API request failed: {e}",
                "Failed to connect to Discord. Please try again.",
            ) from e

    @staticmethod
    async def push_role_connection_metadata(
        access_token: str,
        twitch_username: str,
    ) -> None:
        """
        Push role connection metadata to Discord for a user.

        This updates the user's linked role connection with their Twitch info.

        Args:
            access_token: Discord user access token (with role_connections.write scope)
            twitch_username: User's Twitch username

        Raises:
            DiscordAPIError: Failed to push metadata
        """
        url = f"{DISCORD_API_BASE}/users/@me/applications/{config.discord_oauth_client_id}/role-connection"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "platform_name": "Twitch",
            "platform_username": twitch_username,
            "metadata": {
                "verified_on_twitch": 1,  # Boolean true
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code not in (200, 201):
                    error_data = response.json() if response.content else {}
                    logger.error(
                        f"Failed to push role connection: {response.status_code}, {error_data}"
                    )
                    raise DiscordAPIError(
                        f"Failed to push role connection: {response.status_code}",
                        "Failed to update your Discord profile. Please try again.",
                    )

                logger.info(
                    f"Successfully pushed role connection metadata for Twitch user: {twitch_username}"
                )

        except httpx.RequestError as e:
            logger.error(f"Discord API request error: {e}")
            raise DiscordAPIError(
                f"Discord API request failed: {e}",
                "Failed to connect to Discord. Please try again.",
            ) from e


# Global instance
discord_service = DiscordService()
