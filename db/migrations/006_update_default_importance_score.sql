-- Migration: Update default importance score to 25
-- Date: 2026-02-16
-- Purpose: Change default importance_score from 0.0 to 25 and retroactively update existing records

-- Drop the old constraint and create a new one with the updated default
ALTER TABLE people
ALTER COLUMN importance_score SET DEFAULT 25;

-- Retroactively update all people with importance_score below 25 to ensure minimum baseline
UPDATE people
SET importance_score = GREATEST(importance_score, 25)
WHERE importance_score < 25;
