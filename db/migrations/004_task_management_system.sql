-- Task Management System - Phase 1 MVP
-- Adds foundational tasks table with prioritization and lifecycle management

CREATE TABLE IF NOT EXISTS tasks (
    task_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',

    -- Core content
    title TEXT NOT NULL,
    description TEXT,

    -- Lifecycle management
    status TEXT NOT NULL DEFAULT 'inbox',
    -- Valid values: inbox, next_up, in_progress, blocked, waiting, done, archived

    -- Priority and urgency
    priority INT DEFAULT 0,
    -- Values: 0=none, 1=low, 2=medium, 3=high, 4=urgent
    urgency_score FLOAT DEFAULT 0.0,
    -- Computed score for smart recommendations (recalculated when due_date, priority, or status changes)

    -- Scheduling
    due_date TIMESTAMPTZ,
    defer_until TIMESTAMPTZ,
    -- defer_until: Hide task from active lists until this date
    completed_at TIMESTAMPTZ,

    -- Organization
    project TEXT,
    -- Simple text category: "work", "home", "skippy", etc.
    tags JSONB DEFAULT '[]'::jsonb,
    -- Array of text tags for filtering

    -- Backlog management
    is_backlog BOOLEAN DEFAULT FALSE,
    -- True for long-term "someday/maybe" items
    backlog_rank FLOAT,
    -- Ordering within backlog (lower = higher priority to promote)

    -- Status context
    blocked_reason TEXT,
    -- Why this task is blocked (free text)
    waiting_for TEXT,
    -- What or who we're waiting on

    -- Context and estimation
    energy_level TEXT,
    -- "low", "medium", "high" - helps with smart recommendations
    context TEXT,
    -- Where/how to do it: "@computer", "@home", "@phone", etc.
    estimated_minutes INT,
    -- Time estimate for smart scheduling

    -- Additional info
    notes TEXT,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries (filtered indexes exclude completed/archived tasks)

-- Status-based filtering (for Today panel, getting active tasks)
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks (user_id, status)
    WHERE status NOT IN ('done', 'archived');

-- Due date queries (for overdue checks, due today, etc.)
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks (user_id, due_date)
    WHERE due_date IS NOT NULL AND status NOT IN ('done', 'archived');

-- Backlog filtering (for Backlog panel)
CREATE INDEX IF NOT EXISTS idx_tasks_backlog ON tasks (user_id, backlog_rank)
    WHERE is_backlog = TRUE AND status NOT IN ('done', 'archived');

-- Urgency-based sorting (for "what should I do?" recommendations)
CREATE INDEX IF NOT EXISTS idx_tasks_urgency ON tasks (user_id, urgency_score DESC)
    WHERE status IN ('inbox', 'next_up', 'in_progress');

-- Deferred task filtering (to hide tasks until defer_until date)
CREATE INDEX IF NOT EXISTS idx_tasks_defer ON tasks (user_id, defer_until)
    WHERE defer_until IS NOT NULL AND status NOT IN ('done', 'archived');

-- Project filtering (for project-based views)
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (user_id, project)
    WHERE project IS NOT NULL;

-- Tag-based search (GIN index for JSONB array)
CREATE INDEX IF NOT EXISTS idx_tasks_tags ON tasks USING gin(tags);

-- Composite index for common query patterns (user + status + urgency)
CREATE INDEX IF NOT EXISTS idx_tasks_user_status_urgency ON tasks (user_id, status, urgency_score DESC)
    WHERE status NOT IN ('done', 'archived');
