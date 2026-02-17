-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Semantic memories with vector embeddings
CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    content TEXT NOT NULL,
    embedding vector(1536),
    confidence_score FLOAT NOT NULL DEFAULT 0.5,
    reinforcement_count INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_from_conversation_id TEXT,
    category TEXT,
    person_id INT,
    -- Foreign key to link memory to a specific person (nullable - not all memories are about people)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON semantic_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for filtering active memories by user
CREATE INDEX IF NOT EXISTS idx_memories_user_status
    ON semantic_memories (user_id, status)
    WHERE status = 'active';

-- Index for querying memories by person
CREATE INDEX IF NOT EXISTS idx_memories_person_id
    ON semantic_memories (person_id)
    WHERE person_id IS NOT NULL;

-- Composite index for common query patterns (user + person + category)
CREATE INDEX IF NOT EXISTS idx_memories_user_person_category
    ON semantic_memories (user_id, person_id, category)
    WHERE person_id IS NOT NULL AND status = 'active';

-- Structured people data (Phase 1.1) with identity management (Phase 1.2)
CREATE TABLE IF NOT EXISTS people (
    person_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases JSONB DEFAULT '[]'::jsonb,
    merged_from INT[] DEFAULT '{}',
    relationship TEXT,
    birthday TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    importance_score FLOAT DEFAULT 25,
    last_mentioned TIMESTAMPTZ,
    mention_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_people_user ON people (user_id);
CREATE INDEX IF NOT EXISTS idx_people_aliases ON people USING gin(aliases);
CREATE INDEX IF NOT EXISTS idx_people_importance ON people (user_id, importance_score DESC, last_mentioned DESC);
CREATE INDEX IF NOT EXISTS idx_people_phone ON people (user_id, phone)
  WHERE phone IS NOT NULL AND phone != '';
CREATE INDEX IF NOT EXISTS idx_people_email ON people (user_id, email)
  WHERE email IS NOT NULL AND email != '';
CREATE INDEX IF NOT EXISTS idx_people_last_mentioned ON people (user_id, last_mentioned DESC);

-- Foreign key constraint linking memories to people (migration 005)
ALTER TABLE semantic_memories
    ADD CONSTRAINT fk_memory_person
    FOREIGN KEY (person_id) REFERENCES people(person_id)
    ON DELETE SET NULL;

-- Task Management System (Phase 1 MVP - migration 004)
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

-- Scheduled tasks (chat-created and predefined)
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_config JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Event reminder acknowledgments (Phase 1.3)
CREATE TABLE IF NOT EXISTS reminder_acknowledgments (
    reminder_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    event_id TEXT NOT NULL,
    event_summary TEXT,
    event_start TIMESTAMPTZ NOT NULL,
    reminded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    snoozed_until TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reminders_user_event ON reminder_acknowledgments (user_id, event_id, event_start);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminder_acknowledgments (user_id, status);

-- Activity log for unified event tracking (Phase 2)
CREATE TABLE IF NOT EXISTS activity_log (
    activity_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    activity_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    description TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_user_time ON activity_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log (user_id, activity_type);

-- User preferences for settings (Phase 2)
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY DEFAULT 'nolan',
    theme TEXT DEFAULT 'dark',
    default_page TEXT DEFAULT '/',
    auto_refresh_interval INT DEFAULT 30,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default preferences for nolan
INSERT INTO user_preferences (user_id) VALUES ('nolan')
ON CONFLICT (user_id) DO NOTHING;
