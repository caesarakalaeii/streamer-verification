-- Initial database schema for Discord-Twitch verification bot
-- Version: 001
-- Description: Creates tables for user verifications, OAuth sessions, and audit logging

-- Main verification table: Enforces 1-to-1 mapping between Discord and Twitch users
CREATE TABLE IF NOT EXISTS user_verifications (
    id SERIAL PRIMARY KEY,
    discord_user_id BIGINT NOT NULL UNIQUE,          -- Ensures 1 Discord user = 1 record
    twitch_user_id VARCHAR(255) NOT NULL UNIQUE,     -- Ensures 1 Twitch user = 1 record
    twitch_username VARCHAR(255) NOT NULL,
    twitch_display_name VARCHAR(255),
    verified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_nickname_check TIMESTAMP,
    last_nickname_update TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_discord_user_id ON user_verifications(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_twitch_user_id ON user_verifications(twitch_user_id);

-- OAuth session tracking: Prevents link sharing via dual OAuth flow
CREATE TABLE IF NOT EXISTS oauth_sessions (
    id SERIAL PRIMARY KEY,
    token VARCHAR(64) NOT NULL UNIQUE,               -- Cryptographically secure random token
    discord_user_id BIGINT NOT NULL,                 -- Expected Discord user (from /verify command)
    discord_username VARCHAR(255) NOT NULL,          -- For audit logging
    discord_guild_id BIGINT NOT NULL,                -- Track which server initiated
    expires_at TIMESTAMP NOT NULL,                   -- Token expires after 10 minutes

    -- Step 1: Discord OAuth (Identity Verification)
    discord_oauth_completed BOOLEAN DEFAULT FALSE,   -- Has Discord OAuth been completed?
    discord_oauth_verified_id BIGINT,                -- Actual Discord user ID from OAuth
    discord_oauth_completed_at TIMESTAMP,

    -- Step 2: Twitch OAuth (Account Linking)
    twitch_oauth_completed BOOLEAN DEFAULT FALSE,    -- Has Twitch OAuth been completed?
    twitch_user_id VARCHAR(255),                     -- Twitch user ID from OAuth
    twitch_username VARCHAR(255),                    -- Twitch username from OAuth
    twitch_oauth_completed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for session lookups
CREATE INDEX IF NOT EXISTS idx_oauth_token ON oauth_sessions(token);
CREATE INDEX IF NOT EXISTS idx_oauth_discord_user ON oauth_sessions(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_expires ON oauth_sessions(expires_at) WHERE NOT twitch_oauth_completed;

-- Guild configuration: Per-server settings
CREATE TABLE IF NOT EXISTS guild_config (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL UNIQUE,                 -- Discord guild ID
    guild_name VARCHAR(255) NOT NULL,                -- Guild name (for reference)
    verified_role_id BIGINT NOT NULL,                -- Role ID for verified users
    admin_role_ids TEXT,                             -- Comma-separated admin role IDs
    nickname_enforcement_enabled BOOLEAN DEFAULT TRUE,
    auto_role_assignment_enabled BOOLEAN DEFAULT TRUE,
    nickname_check_interval_seconds INT DEFAULT 300,
    setup_completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    setup_by_user_id BIGINT NOT NULL,               -- User who completed setup
    setup_by_username VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast guild lookups
CREATE INDEX IF NOT EXISTS idx_guild_config_guild_id ON guild_config(guild_id);

-- Audit log for security monitoring and debugging
CREATE TABLE IF NOT EXISTS verification_audit_log (
    id SERIAL PRIMARY KEY,
    discord_user_id BIGINT NOT NULL,
    discord_username VARCHAR(255),
    discord_guild_id BIGINT,                         -- Which guild this action happened in
    twitch_user_id VARCHAR(255),
    twitch_username VARCHAR(255),
    action VARCHAR(50) NOT NULL,                     -- Action type
    reason VARCHAR(255),                             -- Failure reason or additional context
    ip_address INET,                                 -- For security monitoring (optional)
    user_agent TEXT,                                 -- For security monitoring (optional)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for audit log queries
CREATE INDEX IF NOT EXISTS idx_audit_discord_user ON verification_audit_log(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_guild ON verification_audit_log(discord_guild_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON verification_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_created ON verification_audit_log(created_at);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at on user_verifications
DROP TRIGGER IF EXISTS update_user_verifications_updated_at ON user_verifications;
CREATE TRIGGER update_user_verifications_updated_at
    BEFORE UPDATE ON user_verifications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger to update updated_at on guild_config
DROP TRIGGER IF EXISTS update_guild_config_updated_at ON guild_config;
CREATE TRIGGER update_guild_config_updated_at
    BEFORE UPDATE ON guild_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to cleanup expired OAuth sessions
CREATE OR REPLACE FUNCTION cleanup_expired_oauth_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM oauth_sessions
    WHERE expires_at < CURRENT_TIMESTAMP
    AND NOT twitch_oauth_completed;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed for your setup)
-- Note: Replace 'bot_user' with your actual database user
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO bot_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bot_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO bot_user;
