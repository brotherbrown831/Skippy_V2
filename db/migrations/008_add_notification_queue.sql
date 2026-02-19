-- Migration 008: Add notification_queue table for quiet-hours deferred delivery
-- Apply with: docker exec skippy_v2-postgres-1 psql -U skippy -d skippy -f /path/to/008_add_notification_queue.sql

CREATE TABLE IF NOT EXISTS notification_queue (
    queue_id SERIAL PRIMARY KEY,
    tool_name VARCHAR(50) NOT NULL,
    params JSONB NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    error_msg TEXT
);

CREATE INDEX IF NOT EXISTS idx_notif_queue_pending
    ON notification_queue (send_at)
    WHERE status = 'pending';
