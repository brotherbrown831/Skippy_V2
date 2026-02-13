# Skippy V2

An AI personal assistant with long-term semantic memory, built with LangGraph, FastAPI, and PostgreSQL/pgvector. Deploys as a self-contained Docker stack. Named after the magnificently sarcastic AI from the Expeditionary Force book series.

**Replaces** the [Skippy v1](https://github.com/brotherbrown831/Skippy) N8N-based workflows with a proper Python agent framework.

## Architecture

```
                         ┌──────────────────┐
                         │   Input Channels  │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
            ┌───────▼───────┐           ┌───────▼───────┐
            │  HA Voice     │           │  OpenWebUI    │
            │  Pipeline     │           │  Chat         │
            │  (Wyoming)    │           │               │
            └───────┬───────┘           └───────┬───────┘
                    │                           │
                    │  POST /webhook/skippy     │  POST /webhook/v1/chat/completions
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    FastAPI (port 8000)     │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │     LangGraph Agent        │
                    │                            │
                    │  retrieve_memories          │
                    │       ↓                     │
                    │  agent (LLM call)           │
                    │       ↓                     │
                    │  [tools] ←→ agent (loop)    │
                    │       ↓                     │
                    │  evaluate_memory            │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │  PostgreSQL 17 + pgvector   │
                    │  ┌─────────────────────┐   │
                    │  │ checkpoints (state) │   │
                    │  │ semantic_memories   │   │
                    │  └─────────────────────┘   │
                    └───────────────────────────┘
```

## Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | LangGraph (ReAct pattern) |
| LLM | OpenAI gpt-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| HTTP server | FastAPI + Uvicorn |
| Database | PostgreSQL 17 + pgvector |
| Conversation state | langgraph-checkpoint-postgres |
| Deployment | Docker Compose |

## Project Structure

```
├── docker-compose.yml          # Production stack
├── docker-compose.dev.yml      # Dev overlay (hot-reload)
├── Dockerfile
├── .env.example                # Config template
├── pyproject.toml              # Python dependencies
├── db/
│   └── init.sql                # pgvector + semantic_memories schema
└── src/skippy/
    ├── main.py                 # FastAPI app + endpoints
    ├── config.py               # Settings from .env
    ├── agent/
    │   ├── graph.py            # LangGraph graph (the brain)
    │   ├── state.py            # Agent state definition
    │   └── prompts.py          # Skippy personality prompts
    ├── memory/
    │   ├── retriever.py        # pgvector semantic search
    │   └── evaluator.py        # Auto fact extraction + dedup
    └── tools/
        └── home_assistant.py   # HA entity control (placeholder)
```

## Prerequisites

- A **Proxmox LXC or VM** (or any Linux box) with Docker and Docker Compose installed
- An **OpenAI API key** (for gpt-4o-mini and embeddings)
- Your **Home Assistant** instance (for voice — optional for initial testing)

## Deployment Guide

### 1. Prepare the LXC

Create a new LXC container on Proxmox (Ubuntu 22.04+ or Debian 12+ recommended):

```bash
# Install Docker (if not already installed)
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt install docker-compose-plugin

# Verify
docker compose version
```

### 2. Clone the Repo

```bash
git clone https://github.com/brotherbrown831/Skippy_V2.git
cd Skippy_V2
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your values:

```env
# Required — your OpenAI API key
OPENAI_API_KEY=sk-your-actual-key-here

# Database — leave as-is unless you changed docker-compose.yml
DATABASE_URL=postgresql://skippy:skippy@postgres:5432/skippy

# Home Assistant — fill in when ready to connect voice
HA_URL=http://your-ha-ip:8123
HA_TOKEN=your-long-lived-access-token
```

### 4. Start the Stack

**Production:**
```bash
docker compose up -d
```

**Development (hot-reload):**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

In dev mode, any changes you make to files in `src/` will auto-reload the server.

### 5. Verify It's Running

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","agent":"skippy"}

# Test voice endpoint
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "hello skippy", "conversation_id": "test-1", "language": "en", "agent_id": "skippy"}'
# Expected: {"response": "Oh great, another monkey..."} (Skippy personality)

# Test chat endpoint (OpenAI-compatible)
curl -X POST http://localhost:8000/webhook/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "skippy", "messages": [{"role": "user", "content": "hello skippy"}]}'
# Expected: OpenAI-compatible chat completion response
```

### 6. Test Conversation Memory

```bash
# Tell Skippy a fact
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "my dogs name is Max", "conversation_id": "test-memory", "language": "en", "agent_id": "skippy"}'

# Wait a few seconds for memory evaluation to run, then ask about it
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "whats my dogs name", "conversation_id": "test-memory-2", "language": "en", "agent_id": "skippy"}'

# Verify memories in the database
docker compose exec postgres psql -U skippy -c "SELECT content, category, confidence_score, reinforcement_count FROM semantic_memories;"
```

### 7. Connect Home Assistant Voice

Your existing Skippy HA custom component (from the [v1 repo](https://github.com/brotherbrown831/Skippy)) works with v2 — just update the webhook URL:

1. Go to **Settings > Devices & Services** in Home Assistant
2. Find the **Skippy** integration
3. Update the webhook URL to: `http://<skippy-lxc-ip>:8000/webhook/skippy`
4. Talk to Skippy through your Wyoming satellites

### 8. Connect OpenWebUI (Optional)

In OpenWebUI, add a new connection:
- **API Base URL:** `http://<skippy-lxc-ip>:8000/webhook`
- **Model name:** `skippy`
- **API Key:** anything (not validated)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/skippy` | POST | Voice endpoint (HA custom component format) |
| `/webhook/v1/chat/completions` | POST | OpenAI-compatible chat (for OpenWebUI) |

### Voice Endpoint Format

**Request:**
```json
{
  "text": "what's the weather like?",
  "conversation_id": "01HQXYZ...",
  "language": "en",
  "agent_id": "skippy"
}
```

**Response:**
```json
{
  "response": "How should I know? I'm an AI in a beer can, not a weather satellite."
}
```

### Chat Endpoint Format

Standard OpenAI Chat Completions API format. See [OpenAI docs](https://platform.openai.com/docs/api-reference/chat/create).

## Configuration

All configuration is via environment variables (`.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://skippy:skippy@postgres:5432/skippy` |
| `HA_URL` | Home Assistant URL | `http://homeassistant.local:8123` |
| `HA_TOKEN` | HA long-lived access token | empty |
| `LLM_MODEL` | OpenAI model for conversation | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | OpenAI model for embeddings | `text-embedding-3-small` |
| `VOICE_MAX_TOKENS` | Max response tokens for voice | `300` |
| `CHAT_MAX_TOKENS` | Max response tokens for chat | `4096` |
| `MEMORY_SIMILARITY_THRESHOLD` | Min similarity to return a memory | `0.3` |
| `MEMORY_RETRIEVAL_LIMIT` | Max memories to retrieve per query | `5` |
| `MEMORY_DEDUP_THRESHOLD` | Similarity threshold for deduplication | `0.8` |

## Database Schema

The `db/init.sql` file creates the schema automatically on first run. The main table:

```sql
CREATE TABLE semantic_memories (
    memory_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    content TEXT NOT NULL,
    embedding vector(1536),         -- text-embedding-3-small dimensions
    confidence_score FLOAT,
    reinforcement_count INT DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_from_conversation_id TEXT,
    category TEXT,                   -- family, person, preference, project, technical, etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

Conversation history is managed by LangGraph's built-in PostgreSQL checkpointer (tables created automatically on startup).

## How It Works

### Agent Flow

1. **User speaks** into a Wyoming satellite (or types in OpenWebUI)
2. Home Assistant converts speech to text and POSTs to `/webhook/skippy`
3. **Retrieve memories** — embed the query, cosine similarity search against pgvector
4. **Agent reasons** — LLM gets Skippy's personality prompt + relevant memories + conversation history
5. **Tool use** (future) — if the agent decides to use a tool, it executes and loops back
6. **Respond** — text sent back to HA, which converts to speech via TTS
7. **Evaluate memory** — background task asks LLM if the exchange contains facts worth remembering
8. **Store/reinforce** — new facts get embedded and stored; duplicates get reinforced

### Memory System

- **Automatic extraction** — after every conversation turn, an LLM evaluates whether facts were shared
- **Semantic deduplication** — if a new fact is >80% similar to an existing memory, the existing one is reinforced (confidence goes up) instead of creating a duplicate
- **Categorized** — memories are tagged: `family`, `person`, `preference`, `project`, `technical`, `recurring_event`, `fact`
- **Reinforcement** — frequently mentioned facts get higher confidence scores

## Troubleshooting

### Container won't start
```bash
docker compose logs skippy    # Check Python errors
docker compose logs postgres  # Check DB errors
```

### "Connection refused" from HA
- Make sure the LXC IP is reachable from your HA instance
- Check firewall: port 8000 must be open
- Verify with: `curl http://<lxc-ip>:8000/health` from another machine

### Empty or slow responses
- Check your OpenAI API key is valid: `docker compose logs skippy | grep -i error`
- Increase timeout in HA custom component settings if needed

### Reset everything
```bash
docker compose down -v   # Removes containers AND database volume
docker compose up -d     # Fresh start
```

## Roadmap

- [ ] Home Assistant tool use (control lights, thermostats, sensors)
- [ ] Web search tool
- [ ] Calendar integration
- [ ] Proactive notifications (Skippy speaks up when relevant)
- [ ] Multiple user support
- [ ] Local LLM support (Ollama)

## License

MIT
