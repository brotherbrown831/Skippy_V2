-- Migration: Add People Identity Management and Importance Ranking System
-- Date: 2026-02-15
-- Purpose: Support fuzzy identity resolution, aliases, deduplication, and importance tracking

-- Add identity management columns
ALTER TABLE people ADD COLUMN IF NOT EXISTS canonical_name TEXT;
ALTER TABLE people ADD COLUMN IF NOT EXISTS aliases JSONB DEFAULT '[]'::jsonb;
ALTER TABLE people ADD COLUMN IF NOT EXISTS merged_from INT[] DEFAULT '{}';

-- Add importance ranking columns
ALTER TABLE people ADD COLUMN IF NOT EXISTS importance_score FLOAT DEFAULT 0.0;
ALTER TABLE people ADD COLUMN IF NOT EXISTS last_mentioned TIMESTAMPTZ;
ALTER TABLE people ADD COLUMN IF NOT EXISTS mention_count INT DEFAULT 0;

-- Backfill canonical_name with existing name
UPDATE people SET canonical_name = name WHERE canonical_name IS NULL;

-- Make canonical_name required
ALTER TABLE people ALTER COLUMN canonical_name SET NOT NULL;

-- Drop old unique constraint on name (allows temporary duplicates during migration/merge)
DROP INDEX IF EXISTS idx_people_name_user;

-- Create new indexes for identity resolution and importance tracking
CREATE INDEX IF NOT EXISTS idx_people_user ON people (user_id);
CREATE INDEX IF NOT EXISTS idx_people_aliases ON people USING gin(aliases);
CREATE INDEX IF NOT EXISTS idx_people_importance ON people (user_id, importance_score DESC, last_mentioned DESC);
CREATE INDEX IF NOT EXISTS idx_people_phone ON people (user_id, phone)
  WHERE phone IS NOT NULL AND phone != '';
CREATE INDEX IF NOT EXISTS idx_people_email ON people (user_id, email)
  WHERE email IS NOT NULL AND email != '';
CREATE INDEX IF NOT EXISTS idx_people_last_mentioned ON people (user_id, last_mentioned DESC);
