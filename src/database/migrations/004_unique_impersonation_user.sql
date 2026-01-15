-- Migration: Ensure one impersonation detection per Discord user

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY discord_user_id
            ORDER BY detected_at DESC, id DESC
        ) AS rn
    FROM impersonation_detections
)
DELETE FROM impersonation_detections
USING ranked
WHERE impersonation_detections.id = ranked.id
  AND ranked.rn > 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'impersonation_unique_user'
    ) THEN
        ALTER TABLE impersonation_detections
        ADD CONSTRAINT impersonation_unique_user UNIQUE (discord_user_id);
    END IF;
END $$;
