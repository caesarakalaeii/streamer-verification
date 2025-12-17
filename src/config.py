"""Application configuration using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Discord Bot
    discord_bot_token: str = Field(..., description="Discord bot token")

    # Discord OAuth (for Linked Roles)
    # Note: Client ID is same as Application ID, Client Secret from OAuth2 settings
    discord_oauth_client_id: str = Field(
        ..., description="Discord application/client ID"
    )
    discord_oauth_client_secret: str = Field(
        ..., description="Discord OAuth client secret"
    )
    discord_oauth_redirect_uri: str = Field(
        ..., description="Discord OAuth redirect URI"
    )
    discord_linked_role_verification_url: str = Field(
        ..., description="Discord Linked Roles verification URL"
    )

    # Twitch OAuth (for account linking)
    twitch_client_id: str = Field(..., description="Twitch client ID")
    twitch_client_secret: str = Field(..., description="Twitch client secret")
    twitch_redirect_uri: str = Field(..., description="Twitch OAuth redirect URI")

    # Web Server
    web_host: str = Field(default="0.0.0.0", description="Web server host")
    web_port: int = Field(default=8080, description="Web server port")
    web_base_url: str = Field(..., description="Public-facing base URL")

    # Database
    database_host: str = Field(..., description="PostgreSQL host")
    database_port: int = Field(default=5432, description="PostgreSQL port")
    database_name: str = Field(..., description="Database name")
    database_user: str = Field(..., description="Database user")
    database_password: str = Field(..., description="Database password")
    database_pool_size: int = Field(default=10, description="Connection pool size")
    database_max_overflow: int = Field(
        default=20, description="Max overflow connections"
    )

    # Security
    oauth_token_expiry_minutes: int = Field(
        default=10, description="OAuth token expiry in minutes"
    )
    oauth_token_length_bytes: int = Field(
        default=32, description="OAuth token length in bytes"
    )
    session_cleanup_interval_hours: int = Field(
        default=1, description="Session cleanup interval"
    )

    # Bot Behavior
    nickname_check_interval_seconds: int = Field(
        default=300, description="Nickname check interval"
    )
    nickname_update_retry_count: int = Field(
        default=3, description="Nickname update retry count"
    )
    nickname_update_retry_delay_seconds: int = Field(
        default=5, description="Retry delay in seconds"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    log_file_path: str = Field(default="", description="Optional log file path")

    # Feature Flags
    enable_audit_logging: bool = Field(default=True, description="Enable audit logging")
    enable_nickname_enforcement: bool = Field(
        default=True, description="Enable nickname enforcement"
    )
    enable_auto_role_assignment: bool = Field(
        default=True, description="Enable auto role assignment"
    )

    # Development/Debug
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    dry_run_mode: bool = Field(default=False, description="Test without making changes")

    @property
    def database_url(self) -> str:
        """Construct database URL."""
        return f"postgresql+asyncpg://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"


# Global config instance
# Type ignore: pydantic-settings loads from environment variables automatically
config = Config()  # type: ignore[call-arg]
