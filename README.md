# Skippy V2

An AI personal assistant with long-term semantic memory, built with LangGraph, FastAPI, and PostgreSQL/pgvector. Deploys as a self-contained Docker stack. Named after the magnificently sarcastic AI from the Expeditionary Force book series.

**Replaces** the [Skippy v1](https://github.com/brotherbrown831/Skippy) N8N-based workflows with a proper Python agent framework.

## Architecture

```
                        ┌──────────────────────┐
                        │   Input Channels     │
                        └────────┬─────────────┘
                                 │
                   ┌─────────────┼─────────────┐
                   │             │             │
           ┌───────▼───────┐ ┌───▼───┐ ┌──────▼──────┐
           │  HA Voice     │ │Telegram│ │  WhatsApp   │
           │  Pipeline     │ │ Polling│ │   Adapter   │
           │  (Wyoming)    │ │        │ │   (Baileys) │
           └───────┬───────┘ └───┬────┘ └──────┬──────┘
                   │             │             │
                   │  POST /webhook/skippy (all channels)
                   │             │             │
                   └─────────────┴─────────────┤
                                               │
           ┌───────────────────┬───────────────┘
           │                   │
       ┌───▼────────────┐  ┌───▼───────────────┐
       │  OpenWebUI     │  │ FastAPI           │
       │  Chat Endpoint │  │ (port 8000)       │
       └───┬────────────┘  └───────┬───────────┘
           │                       │
           └───────────┬───────────┘
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
                   │  │ people              │   │
                   │  │ tasks               │   │
                   │  └─────────────────────┘   │
                   └───────────────────────────┘
```

## Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | LangGraph (ReAct pattern) |
| Agent LLM | OpenAI gpt-4o-mini (Chat Completions for tool execution) |
| Memory LLM | OpenAI (Responses API for caching efficiency) |
| Embeddings | OpenAI text-embedding-3-small |
| HTTP server | FastAPI + Uvicorn |
| Database | PostgreSQL 17 + pgvector |
| Conversation state | langgraph-checkpoint-postgres |
| Scheduler | APScheduler 3.x |
| SMS | Twilio |
| Google APIs | Calendar, Gmail, Contacts |
| Telegram | Telegram Bot API (long polling) |
| WhatsApp | Baileys library (WhatsApp Web protocol) |
| Web Search | Tavily API (real-time web search) |
| Deployment | Docker Compose |

## Tools (~43 total)

| Module | Tools | Description |
|--------|-------|-------------|
| `google_calendar` | 6 | Read/write calendar events (Google + local ICS files) |
| `gmail` | 5 | Check inbox, search, read, send, reply |
| `google_contacts` | 4 | Search, view, create, update contacts |
| `scheduler` | 4 | Recurring tasks, reminders, timers |
| `people` | 8 | Structured people database CRUD + fuzzy search + identity management |
| `contact_sync` | 1 | Google Contacts → People table sync (scheduled + on-demand) |
| `telegram` | 2 | Receive messages via polling, send notifications |
| `tavily` | 1 | Web search via Tavily API (real-time information) |
| `tasks` | 11 | Task management (CRUD, workflow, priority scoring, scheduling) |
| `communication` | 2 | Send notifications via Telegram + SMS |

## Dashboard Features

Interactive web dashboard with comprehensive features:

| Feature | Description |
|---------|-------------|
| **Semantic Memories** | Full-text search with similarity scoring, categorized facts, reinforcement tracking |
| **People Database** | Contact management with fuzzy duplicate detection, importance scoring, relationship tracking |
| **Task Management** | Two-column layout (Today + Backlog), priority filtering, due date sorting, bulk actions |
| **Recent Activity Timeline** | Unified event log showing last 10 activities across Memories, People, and Tasks with emoji icons |
| **Quick Actions** | Modal forms to create memories (auto-embedded with OpenAI), add people, add tasks |
| **System Health Indicators** | Status badge (🟢 healthy, 🟡 warning, 🔴 error) with detailed metrics modal |
| **Global Search** | Full-width search bar with autocomplete—multi-table fuzzy matching across all systems |
| **User Preferences** | Settings modal with theme toggle (dark/light), default page selection, auto-refresh interval (10-300s) |
| **Statistics Charts** | Professional data visualization: memory growth (30-day line), people importance (bar), entity status (pie) |

**Data backing:** `activity_log` table (unified event tracking) + `user_preferences` table (settings persistence)

## Project Structure

```
├── docker-compose.yml              # Production stack
├── docker-compose.dev.yml          # Dev overlay (hot-reload)
├── Dockerfile
├── pyproject.toml                  # Python dependencies
├── CLAUDE.md                       # Critical instructions (database preservation)
├── ROADMAP.md                      # Feature roadmap and TODOs
├── scripts/
│   └── google_oauth.py             # One-time OAuth2 consent flow
├── credentials/
│   ├── google-sa.json              # Service account (Calendar)
│   ├── google-oauth.json           # OAuth2 client credentials
│   └── google-token.json           # OAuth2 refresh token (Gmail/Contacts)
├── db/
│   └── init.sql                    # Schema initialization
├── tests/                          # Integration test suite (86 tests)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_memory.py
│   ├── test_agent.py
│   ├── test_prompts.py
│   ├── test_tools_*.py
│   └── test_tools_init.py
└── src/skippy/
    ├── main.py                     # FastAPI app + endpoints
    ├── config.py                   # Settings from .env
    ├── agent/
    │   ├── graph.py                # LangGraph graph (the brain)
    │   ├── state.py                # Agent state definition
    │   └── prompts.py              # Skippy personality prompts
    ├── memory/
    │   ├── retriever.py            # pgvector semantic search
    │   └── evaluator.py            # Auto fact extraction + dedup + person linking
    ├── scheduler/
    │   ├── __init__.py             # Scheduler lifecycle
    │   └── routines.py             # Predefined routines (briefings, syncs, etc.)
    ├── tools/
    │   ├── __init__.py             # Tool auto-discovery
    │   ├── google_calendar.py      # Calendar read/write + ICS support
    │   ├── ics_calendar.py         # Local ICS file calendar support
    │   ├── google_auth.py          # Shared OAuth2 helper
    │   ├── gmail.py                # Gmail read/send/reply
    │   ├── google_contacts.py      # Google Contacts CRUD
    │   ├── scheduler.py            # Task & reminder tools
    │   ├── people.py               # Structured people database + fuzzy dedup
    │   ├── tavily.py               # Tavily web search integration
    │   ├── home_assistant.py       # Home Assistant notifications
    │   ├── tasks.py                # Task management
    │   ├── telegram.py             # Telegram bot + notifications
    │   └── testing.py              # Run test suite + email results
    └── web/
        ├── main.py                 # Router registration
        ├── home.py                 # Main dashboard + API endpoints
        ├── memories.py             # Memories tab implementation
        ├── people.py               # People tab implementation
        ├── tasks.py                # Tasks page implementation
        ├── reminders.py            # Reminders management
        ├── calendar.py             # Calendar view
        ├── scheduled.py            # Scheduled jobs view
        └── db_utils.py             # Database utilities
```

## Prerequisites

- A **Linux VM/LXC** (or any Linux box) with Docker and Docker Compose installed
- An **OpenAI API key** (for gpt-4o-mini and embeddings)
- **Google Cloud** service account (Calendar) + OAuth2 credentials (Gmail/Contacts) — optional
- **Twilio** account (SMS) — optional
- **Home Assistant** instance (for voice integration via Wyoming) — optional
- **Tavily API key** (for web search) — optional

## Deployment Guide

### 1. Prepare the System

Create a new VM/LXC on your hypervisor (Ubuntu 22.04+ or Debian 12+ recommended):

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

# Optional — Home Assistant voice integration
HA_URL=http://your-ha-ip:8123
HA_TOKEN=your-long-lived-access-token

# Optional — Telegram notifications
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ALLOWED_CHAT_IDS=your-chat-id

# Optional — Google integrations
GOOGLE_CALENDAR_ID=your-calendar-id@gmail.com
GOOGLE_SERVICE_ACCOUNT_JSON=credentials/google-sa.json
GOOGLE_OAUTH_CLIENT_JSON=credentials/google-oauth.json
GOOGLE_OAUTH_TOKEN_JSON=credentials/google-token.json

# Scheduled job times (HH:MM format or "disabled")
MORNING_BRIEFING_TIME=07:00
EVENING_SUMMARY_TIME=20:00
GOOGLE_CONTACTS_SYNC_TIME=02:00
PEOPLE_IMPORTANCE_RECALC_TIME=23:00
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

In dev mode, changes to files in `src/` will auto-reload the server.

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
```

### 6. Test Conversation Memory

```bash
# Tell Skippy a fact
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "my dogs name is Max", "conversation_id": "test-memory", "language": "en", "agent_id": "skippy"}'

# Wait a few seconds for memory evaluation, then ask about it
curl -X POST http://localhost:8000/webhook/skippy \
  -H "Content-Type: application/json" \
  -d '{"text": "whats my dogs name", "conversation_id": "test-memory-2", "language": "en", "agent_id": "skippy"}'

# Verify memories in the database
docker compose exec postgres psql -U skippy -d skippy -c "SELECT content, category, confidence_score FROM semantic_memories LIMIT 5;"
```

### 7. Connect Home Assistant Voice (Optional)

Update your existing Skippy HA custom component with the new webhook URL:

1. Go to **Settings > Devices & Services** in Home Assistant
2. Find the **Skippy** integration
3. Update the webhook URL to: `http://<skippy-vm-ip>:8000/webhook/skippy`
4. Talk to Skippy through your Wyoming satellites

### 8. Connect Telegram (Optional)

1. Create a bot with @BotFather and get the token
2. Set `TELEGRAM_BOT_TOKEN` in `.env`
3. Optionally set `TELEGRAM_ALLOWED_CHAT_IDS` to restrict access
4. Restart: `docker compose up -d`

Skippy uses long polling (no public webhook required).

### 9. Connect WhatsApp (Optional)

WhatsApp integration uses the WhatsApp Web protocol (Baileys library) — **not** the official Meta Business API. The adapter runs as a separate Docker service and bridges messages to Skippy's HTTP API.

**Setup:**

1. Ensure WhatsApp is installed on your phone (or linked device with existing session)
2. Start the adapter:
   ```bash
   docker compose up -d whatsapp_adapter
   ```

3. View the QR code:
   ```bash
   docker compose logs -f whatsapp_adapter
   ```

   You'll see an ASCII QR code in the logs. Wait for it to stabilize (5-10 seconds).

4. **Link the device on your phone:**
   - Open WhatsApp
   - Go to **Settings** (or **⋯**) → **Linked Devices** (or **Linked Accounts**)
   - Tap **Link a Device**
   - Scan the QR code from the logs

5. Wait for the logs to show: `WhatsApp connection established` → adapter is live

6. Send a WhatsApp message to your phone number — Skippy will respond!

**Optional Configuration** (in `.env`):

```env
# Whitelist specific phone numbers (comma-separated, digits only)
WHATSAPP_ALLOWED_NUMBERS=15551234567,15559876543

# Enable group chat responses (default: disabled, only private chats)
WHATSAPP_ALLOW_GROUPS=false

# Request timeout for Skippy API calls (milliseconds)
SKIPPY_TIMEOUT_MS=30000
```

**Troubleshooting:**

- **No QR code in logs?** Check that the container is running: `docker compose ps whatsapp_adapter`
- **"Session logged out"?** Your phone unlinked the device. Restart the adapter and scan a new QR code.
- **No response to messages?** Check if the message is plain text (images, voice notes are skipped). Look for errors in logs: `docker compose logs whatsapp_adapter`
- **Typing indicator stuck?** This shouldn't happen, but restarting the adapter will clear it: `docker compose restart whatsapp_adapter`

Session files are stored in the `whatsapp_sessions` Docker named volume — they persist across restarts.

### 10. Configure Google Integrations (Optional)

Run the OAuth2 consent flow to generate your refresh token:

```bash
docker compose exec skippy python scripts/google_oauth.py
```

This creates `credentials/google-token.json` for Gmail and Contacts access.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/skippy` | POST | Voice endpoint (HA custom component format) |
| `/webhook/v1/chat/completions` | POST | OpenAI-compatible chat (for OpenWebUI) |
| `/` | GET | Main dashboard |
| `/tasks` | GET | Tasks management page |
| `/calendar` | GET | Calendar view |
| `/api/memories` | GET | Semantic memories JSON API |
| `/api/people` | GET | People database JSON API |
| `/api/tasks` | GET | Tasks JSON API |
| `/api/activity-log` | GET | Activity log JSON API |
| `/api/health` | GET | System health metrics |
| `/api/preferences` | GET/POST | User preferences |
| POST variants for creating/updating resources |

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
    "timestamp": "2026-02-17T00:12:45.940353",
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
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | empty |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | empty |
| `TWILIO_FROM_NUMBER` | Twilio phone number | empty |
| `TWILIO_TO_NUMBER` | Your phone number | empty |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | empty |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated allowed chat IDs | empty |
| `TELEGRAM_NOTIFY_CHAT_IDS` | Comma-separated notification chat IDs | empty |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID | empty |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service account JSON | empty |
| `GOOGLE_OAUTH_CLIENT_JSON` | Path to OAuth2 client credentials | empty |
| `GOOGLE_OAUTH_TOKEN_JSON` | Path to OAuth2 token | empty |
| `TAVILY_API_KEY` | Tavily API key for web search | empty |
| `TAVILY_API_BASE` | Tavily API base URL | `https://api.tavily.com` |
| `LLM_MODEL` | OpenAI model for conversation | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | OpenAI model for embeddings | `text-embedding-3-small` |
| `MORNING_BRIEFING_TIME` | Morning briefing time (HH:MM) | `07:00` |
| `EVENING_SUMMARY_TIME` | Evening summary time (HH:MM) | `20:00` |
| `GOOGLE_CONTACTS_SYNC_TIME` | Contacts sync time (HH:MM) | `02:00` |
| `PEOPLE_IMPORTANCE_RECALC_TIME` | Importance recalculation time (HH:MM) | `23:00` |

## Database Schema

The `db/init.sql` file creates the schema automatically on first run. Main tables:

**semantic_memories** — Semantic facts extracted from conversations
```sql
CREATE TABLE semantic_memories (
    memory_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    content TEXT NOT NULL,
    embedding vector(1536),
    confidence_score FLOAT,
    reinforcement_count INT DEFAULT 0,
    person_id INT REFERENCES people(person_id) ON DELETE SET NULL,
    category TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**people** — Structured contacts with deduplication
```sql
CREATE TABLE people (
    person_id SERIAL PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    aliases JSONB DEFAULT '[]',
    phone TEXT,
    email TEXT,
    birthday DATE,
    importance_score FLOAT DEFAULT 0,
    last_contact_date DATE,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**tasks** — Task and reminder management
```sql
CREATE TABLE tasks (
    task_id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'inbox',
    priority INT DEFAULT 2,
    due_date DATE,
    person_id INT REFERENCES people(person_id),
    category TEXT,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**activity_log** — Unified event tracking
```sql
CREATE TABLE activity_log (
    activity_id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'nolan',
    activity_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id INT,
    description TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

Conversation history is managed by LangGraph's built-in PostgreSQL checkpointer (tables created automatically on startup).

## How It Works

### Agent Flow

1. **User speaks** into a Wyoming satellite (or types in OpenWebUI/Telegram)
2. Input converts to text and POSTs to `/webhook/skippy` (HA), `/webhook/v1/chat/completions` (OpenWebUI), or Telegram
3. **Retrieve memories** — embed the query (Responses API), cosine similarity search against pgvector
4. **Agent reasons** — LLM (Chat Completions) gets Skippy's personality prompt + relevant memories + conversation history
5. **Tool use** — if the agent decides to use a tool (calendar, email, contacts, tasks, web search, etc.), it executes and loops back
6. **Respond** — text sent back to requestor (HA voice TTS, OpenWebUI chat, Telegram message)
7. **Evaluate memory** — background task asks LLM (Responses API) if the exchange contains facts worth remembering
8. **Store/reinforce** — new facts get embedded and stored; duplicates get reinforced and linked to people

### API & LLM Details

**Hybrid Approach for Optimal Performance:**
- **Agent LLM**: OpenAI Chat Completions API — supports structured tool calls needed for LangGraph's agentic loop
- **Memory System**: OpenAI Responses API — 40-80% better cache utilization for memory evaluation and embedding generation
- **Model**: `gpt-4o-mini` (both APIs) — can be upgraded to GPT-5

### Memory System

- **Automatic extraction** — after every conversation turn, an LLM evaluates whether facts were shared
- **Semantic deduplication** — if a new fact is >80% similar to an existing memory, the existing one is reinforced (confidence goes up) instead of creating a duplicate
- **Person linking** — facts mentioning people are automatically linked to the `people` table with 85%+ fuzzy matching confidence
- **Categorized** — memories are tagged: `family`, `person`, `preference`, `project`, `technical`, `recurring_event`, `fact`
- **Reinforcement** — frequently mentioned facts get higher confidence scores

### People Identity Management

- **Fuzzy deduplication** — 5-tier identity resolution (exact phone → exact name → fuzzy ≥85% → fuzzy 70-84% → no match)
- **Aliases** — store alternate names (e.g., "Summer" for "Summer Hollars")
- **Importance scoring** — tracks importance (0-100) with exponential decay (30-day half-life)
- **Google Contacts sync** — daily auto-sync with auto-deduplication and manual merge capability
- **Memory linking** — all memories about a person are linked and queryable

### Task Management

- **Status workflow** — inbox → next_up → in_progress → done (or blocked)
- **Priority scoring** — combines urgency + due date + status + recency
- **Daily briefing** — top 3 actionable tasks + overdue alerts
- **Natural language dates** — "tomorrow", "next Monday", "in 2 weeks"
- **Web integration** — full dashboard view with drag-and-drop, filters, and bulk actions

## Testing

The project includes an integration test suite (86 tests) that hits real services — no mocking.

**Run inside the dev container:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec skippy \
  python -m pytest tests/ -v --tb=short
```

**Or via Skippy himself:**
Ask Skippy to "run the test suite" — he'll execute pytest and email the results.

**What's tested:**
- Config loading and defaults
- PostgreSQL connectivity, pgvector, all tables, memory roundtrip
- Memory retrieval (real OpenAI embeddings + Postgres)
- Agent graph compilation
- Prompt templates
- All tool modules: Google Calendar/Gmail/Contacts, People CRUD, Tasks, Web Search, Telegram
- Tool auto-discovery (`collect_tools()`)
- People identity management (fuzzy matching, merging)
- Task workflows

## Troubleshooting

### Container won't start
```bash
docker compose logs skippy    # Check Python errors
docker compose logs postgres  # Check DB errors
```

### "Connection refused"
- Verify Skippy container is running: `docker compose ps`
- Check network: `docker compose logs skippy | grep -i error`
- Test from another machine: `curl http://<vm-ip>:8000/health`

### Empty or slow responses
- Check your OpenAI API key: `docker compose logs skippy | grep -i error`
- Verify GPU/CPU resources if available
- Check PostgreSQL is responsive: `docker compose exec postgres psql -U skippy -c "SELECT 1;"`

### Database issues
**Important:** See [CLAUDE.md](CLAUDE.md) before running any destructive database operations.

To safely reset with data preservation:
```bash
# Backup current data
docker exec skippy_v2-postgres-1 pg_dump -U skippy skippy > /tmp/skippy_backup.sql

# Restart with fresh schema (keeps data)
docker compose down
docker compose up -d
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the complete feature plan and active enhancements. Key areas:

- **Phase 3**: Event ingestion framework, priority scoring, context awareness
- **Phase 4**: Memory intelligence upgrades, relationship tracking, reflection engine
- **Phase 5**: Calendar optimization, admin dashboard, multi-user support

## License

MIT
