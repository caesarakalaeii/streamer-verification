-- Migration: Add Impersonation Detection Tables
-- Description: Creates tables for impersonation detection system including
--              streamer cache, detection results, and whitelist

-- Create streamer_cache table
CREATE TABLE IF NOT EXISTS streamer_cache (
    id SERIAL PRIMARY KEY,
    twitch_user_id VARCHAR(255) UNIQUE NOT NULL,
    twitch_username VARCHAR(255) NOT NULL,
    twitch_display_name VARCHAR(255),
    follower_count INTEGER DEFAULT 0,
    description TEXT,
    has_discord_link BOOLEAN DEFAULT FALSE,
    profile_image_url VARCHAR(512),
    cached_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    cache_hits INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for streamer_cache
CREATE INDEX IF NOT EXISTS idx_streamer_cache_user_id ON streamer_cache(twitch_user_id);
CREATE INDEX IF NOT EXISTS idx_streamer_cache_username ON streamer_cache(LOWER(twitch_username));
CREATE INDEX IF NOT EXISTS idx_streamer_cache_last_updated ON streamer_cache(last_updated);

-- Create impersonation_detections table
CREATE TABLE IF NOT EXISTS impersonation_detections (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,

    -- Suspected impersonator
    discord_user_id BIGINT NOT NULL,
    discord_username VARCHAR(255),
    discord_display_name VARCHAR(255),
    discord_account_age_days INTEGER NOT NULL,
    discord_bio TEXT,

    -- Suspected streamer
    suspected_streamer_id VARCHAR(255) NOT NULL,
    suspected_streamer_username VARCHAR(255) NOT NULL,
    suspected_streamer_follower_count INTEGER DEFAULT 0,

    -- Scoring
    total_score INTEGER NOT NULL,
    username_similarity_score INTEGER NOT NULL,
    account_age_score INTEGER NOT NULL,
    bio_match_score INTEGER NOT NULL,
    streamer_popularity_score INTEGER NOT NULL,
    discord_absence_score INTEGER NOT NULL,
    risk_level VARCHAR(20) NOT NULL,

    -- Detection metadata
    detection_trigger VARCHAR(50),
    detected_at TIMESTAMP DEFAULT NOW(),

    -- Moderation
    status VARCHAR(50) DEFAULT 'pending',
    reviewed_by_user_id BIGINT,
    reviewed_by_username VARCHAR(255),
    reviewed_at TIMESTAMP,
    moderator_action VARCHAR(50),
    moderator_notes TEXT,
    alert_message_id BIGINT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for impersonation_detections
CREATE INDEX IF NOT EXISTS idx_impersonation_discord_user ON impersonation_detections(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_impersonation_guild_status ON impersonation_detections(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_impersonation_risk_detected ON impersonation_detections(risk_level, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_impersonation_streamer ON impersonation_detections(suspected_streamer_id);

-- Create impersonation_whitelist table
CREATE TABLE IF NOT EXISTS impersonation_whitelist (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    discord_username VARCHAR(255),
    reason VARCHAR(255),
    added_by_user_id BIGINT,
    added_by_username VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, discord_user_id)
);

-- Index for impersonation_whitelist
CREATE INDEX IF NOT EXISTS idx_whitelist_guild_user ON impersonation_whitelist(guild_id, discord_user_id);

-- Extend guild_config table with impersonation detection settings
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_detection_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_min_score_threshold INTEGER DEFAULT 60;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_moderation_channel_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_alert_only_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_auto_quarantine_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_quarantine_role_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_auto_dm_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS impersonation_trusted_role_ids TEXT;

-- Seed streamer_cache from existing verifications
INSERT INTO streamer_cache (twitch_user_id, twitch_username, twitch_display_name)
SELECT DISTINCT twitch_user_id, twitch_username, twitch_display_name
FROM user_verifications
ON CONFLICT (twitch_user_id) DO NOTHING;
