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
| Scheduler | APScheduler 3.x |
| SMS | Twilio |
| Google APIs | Calendar (service account), Gmail + Contacts (OAuth2) |
| Telegram | Telegram Bot API (long polling) |
| Deployment | Docker Compose |

## Tools (26 total)

| Module | Tools | Description |
|--------|-------|-------------|
| `home_assistant` | 2 | Push notifications (HA), SMS (Twilio) |
| `google_calendar` | 6 | Read/write calendar events |
| `gmail` | 5 | Check inbox, search, read, send, reply |
| `google_contacts` | 4 | Search, view, create, update contacts |
| `scheduler` | 4 | Recurring tasks, reminders, timers |
| `people` | 5 | Structured people database CRUD |
| `telegram` | 1 | Send Telegram messages |

## Project Structure

```
├── docker-compose.yml          # Production stack
├── docker-compose.dev.yml      # Dev overlay (hot-reload)
├── Dockerfile
├── pyproject.toml              # Python dependencies
├── scripts/
│   └── google_oauth.py         # One-time OAuth2 consent flow
├── credentials/
│   ├── google-sa.json          # Service account (Calendar)
│   ├── google-oauth.json       # OAuth2 client credentials
│   └── google-token.json       # OAuth2 refresh token (Gmail/Contacts)
├── db/
│   └── init.sql                # Schema: memories, people, scheduled_tasks
└── src/skippy/
    ├── main.py                 # FastAPI app + endpoints
    ├── config.py               # Settings from .env
    ├── agent/
    │   ├── graph.py            # LangGraph graph (the brain)
    │   ├── state.py            # Agent state definition
    │   └── prompts.py          # Skippy personality prompts
    ├── memory/
    │   ├── retriever.py        # pgvector semantic search
    │   └── evaluator.py        # Auto fact extraction + dedup + person extraction
    ├── scheduler/
    │   ├── __init__.py          # Scheduler lifecycle
    │   └── routines.py          # Predefined routines (morning briefing, etc.)
    ├── tools/
    │   ├── __init__.py          # Tool auto-discovery
    │   ├── home_assistant.py    # Push notifications + SMS
    │   ├── google_calendar.py   # Calendar read/write
    │   ├── google_auth.py       # Shared OAuth2 helper
    │   ├── gmail.py             # Gmail read/send/reply
    │   ├── google_contacts.py   # Google Contacts CRUD
    │   ├── scheduler.py         # Task & reminder tools
    │   └── people.py            # Structured people database
    └── web/
        ├── memories.py          # Memory Bank dashboard (tabbed)
        └── people.py            # People API endpoints
```

## Prerequisites

- A **Proxmox LXC or VM** (or any Linux box) with Docker and Docker Compose installed
- An **OpenAI API key** (for gpt-4o-mini and embeddings)
- **Home Assistant** instance (for voice + push notifications — optional)
- **Google Cloud** service account (Calendar) + OAuth2 credentials (Gmail/Contacts — optional)
- **Twilio** account (SMS — optional)

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

### 9. Connect Telegram (Optional)

1. Create a bot with @BotFather and get the token
2. Set `TELEGRAM_BOT_TOKEN` in `.env`
3. (Optional) Set `TELEGRAM_ALLOWED_CHAT_IDS` to restrict who can talk to Skippy
4. Restart the stack (`docker compose up -d`)

Skippy uses long polling, so no public webhook is required.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/skippy` | POST | Voice endpoint (HA custom component format) |
| `/webhook/v1/chat/completions` | POST | OpenAI-compatible chat (for OpenWebUI) |
| `/memories` | GET | Memory Bank web dashboard |
| `/api/memories` | GET | Semantic memories JSON API |
| `/api/people` | GET | People database JSON API |

### Voice Endpoint Format

The endpoint accepts both the HA custom component format and a simpler direct format.

**HA Custom Component Request (what Home Assistant sends):**
```json
{
  "input_text": "what's the weather like?",
  "conversation_id": "01HQXYZ...",
  "session_id": "01HQXYZ...",
  "source": "ha_assist",
  "context": {
    "language": "en",
    "timestamp": "2026-02-14T00:12:45.940353",
    "agent_id": "SkippyV2"
  }
}
```

**Direct API Request (for testing):**
```json
{
  "text": "what's the weather like?",
  "conversation_id": "01HQXYZ...",
  "language": "en",
  "agent_id": "skippy"
}
```

**Response (both formats return this):**
```json
{
  "response": "How should I know? I'm an AI in a beer can, not a weather satellite.",
  "response_text": "How should I know? I'm an AI in a beer can, not a weather satellite."
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
| `HA_NOTIFY_SERVICE` | HA mobile app service name | empty |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | empty |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | empty |
| `TWILIO_FROM_NUMBER` | Twilio phone number (e.g., +15551234567) | empty |
| `TWILIO_TO_NUMBER` | Your phone number | empty |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | empty |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated allowed chat IDs | empty |
| `TELEGRAM_NOTIFY_CHAT_IDS` | Comma-separated chat IDs for proactive messages | empty |
| `TELEGRAM_POLL_INTERVAL` | Polling backoff seconds | `2` |
| `TELEGRAM_LONG_POLL_TIMEOUT` | Long polling timeout seconds | `20` |
| `TELEGRAM_API_BASE` | Telegram API base URL | `https://api.telegram.org` |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID | empty |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service account JSON | empty |
| `GOOGLE_OAUTH_CLIENT_JSON` | Path to OAuth2 client credentials | empty |
| `GOOGLE_OAUTH_TOKEN_JSON` | Path to OAuth2 token (generated by `scripts/google_oauth.py`) | empty |
| `LLM_MODEL` | OpenAI model for conversation | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | OpenAI model for embeddings | `text-embedding-3-small` |
| `VOICE_MAX_TOKENS` | Max response tokens for voice | `300` |
| `CHAT_MAX_TOKENS` | Max response tokens for chat | `4096` |
| `MEMORY_SIMILARITY_THRESHOLD` | Min similarity to return a memory | `0.15` |
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
5. **Tool use** — if the agent decides to use a tool (calendar, email, contacts, SMS, etc.), it executes and loops back
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

See [ROADMAP.md](ROADMAP.md) for the full 4-phase plan. Key remaining items:

- [ ] Structured events/gifts/locations tables
- [ ] Escalating reminders (repeat until acknowledged)
- [ ] Event ingestion framework (email, sensors, financial alerts)
- [ ] Priority scoring engine
- [ ] Context awareness (time-of-day, meeting status)
- [ ] Memory intelligence 2.0 (decay, recency weighting)
- [ ] Admin dashboard
- [ ] Multiple user support

## License

MIT
