"""Application constants."""

# Audit Log Actions
AUDIT_ACTION_VERIFY_INITIATED = "verify_initiated"
AUDIT_ACTION_VERIFY_SUCCESS = "verify_success"
AUDIT_ACTION_VERIFY_FAILED = "verify_failed"
AUDIT_ACTION_UNVERIFY = "unverify"
AUDIT_ACTION_NICKNAME_UPDATED = "nickname_updated"
AUDIT_ACTION_DISCORD_OAUTH_COMPLETED = "discord_oauth_completed"
AUDIT_ACTION_TWITCH_OAUTH_COMPLETED = "twitch_oauth_completed"

# Impersonation Detection Audit Actions
AUDIT_ACTION_IMPERSONATION_DETECTED = "impersonation_detected"
AUDIT_ACTION_IMPERSONATION_BANNED = "impersonation_banned"
AUDIT_ACTION_IMPERSONATION_KICKED = "impersonation_kicked"
AUDIT_ACTION_IMPERSONATION_WARNED = "impersonation_warned"
AUDIT_ACTION_IMPERSONATION_MARKED_SAFE = "impersonation_marked_safe"
AUDIT_ACTION_IMPERSONATION_FALSE_POSITIVE = "impersonation_false_positive"
AUDIT_ACTION_IMPERSONATION_WHITELISTED = "impersonation_whitelisted"

# OAuth Configuration
DISCORD_OAUTH_SCOPES = [
    "identify",
    "role_connections.write",
]  # Linked Roles requires role_connections.write
TWITCH_OAUTH_SCOPES = ["user:read:email"]

# Discord API Endpoints
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = f"{DISCORD_API_BASE}/oauth2/authorize"
DISCORD_OAUTH_TOKEN = f"{DISCORD_API_BASE}/oauth2/token"
DISCORD_USERS_ME = f"{DISCORD_API_BASE}/users/@me"

# Twitch API Endpoints
TWITCH_OAUTH_AUTHORIZE = "https://id.twitch.tv/oauth2/authorize"
TWITCH_OAUTH_TOKEN = "https://id.twitch.tv/oauth2/token"
TWITCH_HELIX_USERS = "https://api.twitch.tv/helix/users"
TWITCH_HELIX_CHANNELS = "https://api.twitch.tv/helix/channels"
TWITCH_HELIX_FOLLOWERS = "https://api.twitch.tv/helix/channels/followers"
TWITCH_HELIX_SEARCH_CHANNELS = "https://api.twitch.tv/helix/search/channels"

# Error Messages
ERROR_TOKEN_EXPIRED = "Your verification link has expired. Please run /verify again."
ERROR_TOKEN_INVALID = "Invalid verification link. Please run /verify again."
ERROR_TOKEN_ALREADY_USED = (
    "This verification link has already been used. Please run /verify again."
)
ERROR_DISCORD_MISMATCH = "This verification link belongs to a different Discord user."
ERROR_DISCORD_OAUTH_NOT_COMPLETED = (
    "Discord authentication not completed. Please start over."
)
ERROR_TWITCH_ALREADY_LINKED = (
    "This Twitch account is already linked to another Discord user."
)
ERROR_DISCORD_ALREADY_LINKED = "Your Discord account is already linked to a different Twitch account. Use /unverify first to change."
ERROR_ALREADY_VERIFIED = "You are already verified as {twitch_username}."
ERROR_NO_PERMISSION_NICKNAME = (
    "Bot lacks permission to manage nicknames. Please contact an administrator."
)
ERROR_NO_PERMISSION_ROLE = (
    "Bot lacks permission to manage roles. Please contact an administrator."
)

# Success Messages
SUCCESS_VERIFICATION_COMPLETE = "✅ Successfully verified as {twitch_username}! You can close this page and return to Discord."
SUCCESS_DISCORD_VERIFIED = (
    "✅ Discord identity verified. Now please authenticate with Twitch."
)
