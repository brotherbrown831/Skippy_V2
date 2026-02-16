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
