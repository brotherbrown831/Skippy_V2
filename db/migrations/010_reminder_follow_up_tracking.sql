-- Migration 010: Add follow-up tracking columns to reminder_acknowledgments
-- Enables the follow_up_pending_reminders scheduler job to re-send reminders
-- that remain pending, with rate limiting and retry caps.

ALTER TABLE reminder_acknowledgments
    ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0;
