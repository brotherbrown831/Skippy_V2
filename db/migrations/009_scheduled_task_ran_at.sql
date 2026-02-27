-- Migration 009: Add ran_at timestamp to scheduled_tasks
-- One-time (date-type) tasks are marked with ran_at after they fire,
-- so the UI can show "Ran on ..." instead of leaving them as "Enabled".

ALTER TABLE scheduled_tasks
    ADD COLUMN IF NOT EXISTS ran_at TIMESTAMPTZ;
