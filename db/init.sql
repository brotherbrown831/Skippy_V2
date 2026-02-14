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
