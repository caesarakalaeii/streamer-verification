"""Twitch OAuth API client service."""

import logging
from typing import Any

import httpx

from src.config import config
from src.shared.constants import (
    TWITCH_HELIX_USERS,
    TWITCH_OAUTH_AUTHORIZE,
    TWITCH_OAUTH_SCOPES,
    TWITCH_OAUTH_TOKEN,
)
from src.shared.exceptions import TwitchAPIError

logger = logging.getLogger(__name__)


class TwitchService:
    """Service for Twitch OAuth API interactions."""

    @staticmethod
    def get_oauth_url(token: str) -> str:
        """
        Generate Twitch OAuth authorization URL.

        Args:
            token: State parameter (OAuth session token)

        Returns:
            Full OAuth authorization URL
        """
        scopes = " ".join(TWITCH_OAUTH_SCOPES)
        params = {
            "client_id": config.twitch_client_id,
            "redirect_uri": config.twitch_redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": token,
        }
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{TWITCH_OAUTH_AUTHORIZE}?{param_str}"
        logger.debug(f"Generated Twitch OAuth URL with state={token[:8]}...")
        return url

    @staticmethod
    async def exchange_code_for_token(code: str) -> str:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Access token

        Raises:
            TwitchAPIError: Failed to exchange code
        """
        data = {
            "client_id": config.twitch_client_id,
            "client_secret": config.twitch_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.twitch_redirect_uri,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    TWITCH_OAUTH_TOKEN,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10.0,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    logger.error(f"Twitch token exchange failed: {response.status_code}, {error_data}")
                    raise TwitchAPIError(
                        f"Failed to exchange code for token: {response.status_code}",
                        "Failed to authenticate with Twitch. Please try again.",
                    )

                token_data = response.json()
                access_token = token_data.get("access_token")

                if not access_token:
                    logger.error(f"No access token in Twitch response: {token_data}")
                    raise TwitchAPIError(
                        "No access token in response",
                        "Failed to authenticate with Twitch. Please try again.",
                    )

                logger.info("Successfully exchanged Twitch code for access token")
                return access_token

        except httpx.RequestError as e:
            logger.error(f"Twitch API request error: {e}")
            raise TwitchAPIError(
                f"Twitch API request failed: {e}",
                "Failed to connect to Twitch. Please try again.",
            ) from e

    @staticmethod
    async def get_user_info(access_token: str) -> dict[str, Any]:
        """
        Fetch Twitch user information using access token.

        Args:
            access_token: Twitch access token

        Returns:
            User info dict with 'id', 'login', 'display_name', etc.

        Raises:
            TwitchAPIError: Failed to fetch user info
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": config.twitch_client_id,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    TWITCH_HELIX_USERS,
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    logger.error(f"Twitch user info fetch failed: {response.status_code}, {error_data}")
                    raise TwitchAPIError(
                        f"Failed to fetch user info: {response.status_code}",
                        "Failed to fetch your Twitch information. Please try again.",
                    )

                response_data = response.json()
                data = response_data.get("data", [])

                if not data:
                    logger.error(f"No user data in Twitch response: {response_data}")
                    raise TwitchAPIError(
                        "No user data in response",
                        "Failed to fetch your Twitch information. Please try again.",
                    )

                user_data = data[0]
                logger.info(f"Fetched Twitch user info: {user_data.get('id')} ({user_data.get('login')})")
                return user_data

        except httpx.RequestError as e:
            logger.error(f"Twitch API request error: {e}")
            raise TwitchAPIError(
                f"Twitch API request failed: {e}",
                "Failed to connect to Twitch. Please try again.",
            ) from e


# Global instance
twitch_service = TwitchService()
