-- Migration: Enable pg_trgm extension and create trigram index on streamer cache

-- Enable pg_trgm for similarity search (safe to run multiple times)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Index that powers fast trigram searches on Twitch usernames
CREATE INDEX IF NOT EXISTS idx_streamer_cache_username_trgm
    ON streamer_cache USING gin (twitch_username gin_trgm_ops);
