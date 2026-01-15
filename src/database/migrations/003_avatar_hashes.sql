-- Migration: Add avatar hash and match score for impersonation detection

ALTER TABLE streamer_cache
ADD COLUMN IF NOT EXISTS profile_image_hash BIGINT;

ALTER TABLE impersonation_detections
ADD COLUMN IF NOT EXISTS avatar_match_score INTEGER NOT NULL DEFAULT 0;
