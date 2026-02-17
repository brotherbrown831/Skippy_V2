# Skippy V2 Roadmap

> Long-term vision for Skippy — from reactive assistant to proactive, context-aware AI.
> This is a living document. Not everything here will be built at once.

## Current State (Feb 2026)

✅ **Core Agent & Memory System:**
- LangGraph agent with ReAct pattern (gpt-4o-mini via Chat Completions for tool execution, Responses API for memory caching)
- FastAPI backend with voice webhook + OpenAI-compatible chat endpoint
- PostgreSQL 17 + pgvector semantic memory (store, retrieve, dedup)
- langgraph-checkpoint-postgres for conversation persistence
- Sarcastic Skippy personality with voice/chat/Telegram modes

✅ **Structured Life Data Layer:**
- **People database**: 250+ contacts with fuzzy deduplication (5-tier identity resolution)
  - Aliases support (e.g., "Summer" for "Summer Hollars")
  - Importance scoring (0-100) with exponential decay (30-day half-life)
  - Bidirectional linking to semantic memories
- **Google Contacts sync**: Daily auto-sync (2 AM) + on-demand trigger
  - Auto-merges duplicates, strips ICE labels
- **Memory-Person linking**: All facts about a person are queryable via person record
- **Fuzzy matching**: token_set_ratio algorithm (handles partial names well)

✅ **Task Management System (Phase 1 MVP):**
- Full CRUD operations for tasks
- Status workflow: inbox → next_up → in_progress → done (or blocked)
- Priority scoring: combines urgency + due date + status
- Natural language date parsing ("tomorrow", "next Monday", "in 2 weeks")
- Daily briefing integration (top 3 actionable tasks + overdue alerts)
- 11 tools total for task management
- Web dashboard with two-column layout (Today + Backlog)

✅ **Communication Channels:**
- Push notifications via Home Assistant Companion (configured, working)
- SMS via Twilio (working)
- Telegram bot with long-polling (receive + send)

✅ **Google Integrations:**
- Google Calendar: 6 tools (read/write via service account)
- Gmail: 5 tools (read inbox, search, read, send, reply via OAuth2)
- Google Contacts: 4 tools (search, view, create, update via OAuth2)
- OAuth2 consent flow automation (`scripts/google_oauth.py`)

✅ **Web Search Integration:**
- Tavily API for real-time web search
- One tool: `search_web()` with Tavily backend
- Optional feature with graceful degradation if API key not configured
- Returns formatted results with titles, snippets, and URLs

✅ **Dashboard Phase 2 (6 Advanced Features):**
- **Recent Activity Timeline**: Unified event log (Memories, People, Tasks) with emoji icons
- **Quick Actions**: Modal forms for creating memories + people
- **System Health Indicators**: Status badge (🟢/🟡/🔴) with metrics modal
- **Global Search**: Multi-table fuzzy search with relevance scoring
- **User Preferences**: Persistent theme, default page, auto-refresh interval
- **Statistics Charts**: Memory growth (30-day line), people importance (bar), status (pie)

✅ **Activity Logging Infrastructure:**
- Unified event tracking across all subsystems
- `activity_log` table with automatic logging
- 30+ functions instrumented (memory, people, tasks, syncs)
- Real-time dashboard updates

✅ **Configurable Job Scheduler:**
- All job times configurable via `.env`
- `MORNING_BRIEFING_TIME`, `EVENING_SUMMARY_TIME`, `GOOGLE_CONTACTS_SYNC_TIME`, `PEOPLE_IMPORTANCE_RECALC_TIME`
- Support for "disabled" keyword to skip jobs
- Pydantic validation with helpful error messages
- Dynamic CronTrigger construction

✅ **Calendar Optimization:**
- 30-minute check interval (was 60 min — 2x more responsive)
- Compressed reminder prompt: 322 → 70 tokens (78% reduction)
- 57% daily token savings despite 2x frequency increase
- Terse format while preserving all logic

✅ **ICS Calendar Support (New Feb 2026):**
- Local ICS file calendar reading
- Dual calendar source: Google Calendar + local ICS files
- Tools: `ics_calendar.py` module with read operations

✅ **Test Suite:**
- 86 comprehensive integration tests (hits real services, no mocking)
- pytest + pytest-asyncio
- All tests passing with zero warnings
- Covers: config, database, memory, agent, prompts, all tool modules

✅ **Removed Features (Refocus as Personal Assistant Feb 2026):**
- Removed 17 HA device control tools
- Removed 3 entity management tools
- Removed entity resolution system, WebSocket client
- Removed ha_entities table, persistent entity tracking
- Tool count reduced: 61 → ~43
- DB cleanup: 3 tables dropped
- ~2,921 lines of HA code removed
- Preserved: voice integration (Wyoming), notifications, SMS

---

## Phase 3 — Awareness & Monitoring

### Phase 3.1: Event Ingestion Framework

Standardized way to ingest events from external sources. Everything becomes a normalized event instead of hardcoding each integration.

**Status:** 🔵 Not started

**Design:**
- Normalized event format: `{source, type, payload, timestamp, confidence}`
- Enable scaling: new integrations just emit events in standard format

**Event sources to integrate:**
- Email triggers (Gmail forwarding rules)
- Home Assistant sensors + automations
- Calendar changes
- Financial alerts (bank/stocks)
- Camera alerts
- Stock price changes
- Weather extremes

**Implementation approach:**
1. Define event schema + validation
2. Create event bus (in-memory + optional message queue)
3. Event handlers for each source
4. Test with 3-4 source types initially

---

### Phase 3.2: Priority Scoring Engine

Every incoming event gets scored to determine if and how to notify.

**Status:** 🔵 Not started

**Scoring factors:**
- Urgency (critical/high/medium/low)
- Historical sensitivity (how often user cares about this type)
- Context (time, calendar state, location)
- Sender importance (people table importance_score)
- Deviation from normal patterns

**Output:**
- Score: 0-100
- If > threshold: trigger notification at appropriate level
- Enables selective filtering (reduces noise)

**Depends on:** Phase 3.1 (Event Ingestion)

---

### Phase 3.3: Context Awareness Layer

Add context weighting so the same event means different things in different circumstances.

**Status:** 🔵 Not started

**Context signals to track:**
- Time of day (business hours vs. sleeping)
- Meeting status (in meeting vs. free)
- Location (home, office, driving, away)
- Sleep schedule (quiet hours)
- Family member context (is someone else home?)

**Example use case:**
- Garage opens at 2 AM = critical alert ⚠️
- Garage opens at 5 PM = ignore (expected)

**Implementation:**
1. Expand `user_preferences` table to include context states
2. Create context inference engine (from calendar + HA or user input)
3. Weight priority scores by context

**Depends on:** Phase 3.2 (Priority Scoring)

---

## Phase 4 — Intelligence Upgrade

### Phase 4.1: Memory Intelligence 2.0

Enhance the existing semantic memory system with smarter retrieval and lifecycle management.

**Status:** 🔵 Not started

**Enhancements:**
- **Recency weighting**: newer memories rank higher in search results
- **Importance reinforcement**: frequently accessed facts = more important
- **Time decay**: old, unused memories gradually fade in relevance
- **Category weighting**: some categories matter more in certain contexts
  - e.g., in a meeting, prioritize `technical` over `preference`
- **Cross-memory linking**: connect related facts with a relationship graph
- **Temporal patterns**: detect cyclical facts (birthdays, anniversaries)

**Implementation approach:**
1. Add `last_accessed`, `importance_weight` fields to `semantic_memories`
2. Update retrieval query to apply decay + recency weighting
3. Create memory linking algorithm (semantic + keyword-based)
4. Implement category context weights

**Goal:** Skippy remembers like a human — recent and important things surface first, old irrelevant things fade.

---

### Phase 4.2: Long-Term Relationship Tracking

Build on the structured people data to track relationship patterns over time.

**Status:** 🔵 Not started

**Track per person:**
- Last contact date (calculated from messages/calls)
- Gift history (who gave what, when)
- Communication patterns (how often you talk, preferred channel)
- Shared interests (from memory linking)
- Important dates (birthdays, anniversaries)

**New tables:**
- `gifts`: person, date, item, source, occasion
- `contact_events`: person, type, timestamp, channel (call/message/email)
- `relationship_metrics`: person, recency_score, interaction_frequency, last_interaction_date

**Enables:**
- "You haven't talked to Mark in 3 months."
- "You bought Hera Legos last year."
- Automatic gift reminders before important dates
- "Show me people I haven't talked to recently"
- Holiday/birthday reminders with historical context

**Depends on:** Phase 1.1 (Structured Life Data) ✅, Phase 4.1 (Memory Intelligence 2.0)

---

### Phase 4.3: Reflection & Summary Engine

Periodic self-analysis to increase long-term usefulness.

**Status:** 🔵 Not started

**Capabilities:**
- **Weekly summaries**: Activity and events from the past week
- **Missed event analysis**: Detected events you should have been reminded about but weren't
- **Behavioral trend detection**: Patterns in your habits, interests, communication
- **Important signal identification**: Which recurring signals are most valuable to track

**Implementation approach:**
1. Create weekly reflection job (Sunday evening)
2. Use LLM (Responses API) with 6-month activity summaries
3. Output: structured summary + trend insights + suggestions
4. Store summaries in memory table for long-term tracking

**Depends on:** Phase 3 (Awareness), Phase 4.1 (Memory Intelligence 2.0)

---

## Phase 5 — Expansion & Admin

### Phase 5.1: Calendar Deep Integration

Full read/write access is done (6 calendar tools via service account). Remaining enhancements:

**Status:** 🟡 Partially done (read/write complete, enhancements pending)

**Remaining features:**
- **Conflict detection**: Alert when you're double-booked or meetings overlap
- **Suggestion engine**: "You have a gap Tuesday afternoon from 2-4 PM"
- **Auto-scheduling**: Suggest optimal times for new tasks based on calendar gaps
- **Calendar analytics**: Meeting load, free time trends, most common attendees
- **Time blocking**: Auto-create focus time blocks for high-priority tasks

**Implementation approach:**
1. Add calendar query tools (list free slots, detect conflicts)
2. Create scheduling suggestion algorithm
3. Integrate with task priority scoring for auto-scheduling

---

### Phase 5.2: Admin Dashboard

Observability layer for managing Skippy.

**Status:** 🔵 Not started

**Admin view features:**
- **Memory management**: View/edit/delete specific memories, bulk operations
- **Structured life graph**: Visualize people, events, gifts, relationships
- **Active reminders & tasks**: See what's scheduled and when
- **Event ingestion logs**: Trace recent events, debug integrations
- **Escalation history**: See which reminders were escalated and why
- **Tool usage stats**: Which tools are used most, error rates
- **Performance metrics**: Response times, token usage, API call costs
- **Config UI**: Change settings without editing `.env`

**Implementation approach:**
1. Create `/admin` protected route
2. Build React dashboard with tabs for each view
3. Add admin-only API endpoints
4. Optional: Multi-user auth for admin access

**Depends on:** Phase 1-4 (data accumulation)

---

### Phase 5.3: Multi-User Support

Expand from single-user (`user_id = 'nolan'`) to multi-user system.

**Status:** 🔵 Not started

**Required changes:**
- User authentication (OAuth2 or simple login)
- Row-level security: users only see their own data
- Separate conversation histories per user
- Separate activity logs, preferences, reminders
- Multi-tenant database design

**Implementation approach:**
1. Add `users` table with auth credentials + settings
2. Update all tables to include `user_id` foreign key
3. Add auth middleware to FastAPI
4. Create login endpoint + session management
5. Test with 2-3 user accounts

**Nice to have:**
- Shared calendars / shared memories between users
- Family group access with permission levels

---

## Dependency Map

```
Phase 1: Foundation ✅
├─ 1.1: Structured Data (people, tasks) ✅
├─ 1.2: Task/Reminder Engine ✅
└─ 1.3: Notification System ✅

Phase 2: Dashboard & UX ✅
├─ Activity logging ✅
├─ Preferences persistence ✅
├─ Charts & analytics ✅
└─ Global search ✅

Phase 3: Awareness & Monitoring
├─ 3.1: Event Ingestion Framework
├─ 3.2: Priority Scoring (depends on 3.1)
├─ 3.3: Context Awareness (depends on 3.2)
└─ Morning Briefing 2.0 (integrates with all above)

Phase 4: Intelligence Upgrade
├─ 4.1: Memory Intelligence 2.0
├─ 4.2: Relationship Tracking (depends on 4.1)
└─ 4.3: Reflection Engine (depends on 3.x + 4.1)

Phase 5: Expansion
├─ 5.1: Calendar Enhancements
├─ 5.2: Admin Dashboard (depends on 1-4)
└─ 5.3: Multi-User Support
```

---

## How to Contribute

See [CLAUDE.md](CLAUDE.md) for critical instructions on database preservation. When implementing features:

1. **Read CLAUDE.md first** — database safety is paramount
2. **Check dependencies** — ensure prerequisites above are complete
3. **Test thoroughly** — add tests to the suite (currently 86 tests)
4. **Update documentation** — keep README and this roadmap in sync
5. **Commit carefully** — use meaningful messages, reference completed features

---

## Known Issues

- **HA Notifications not delivering** (Feb 4 onwards): API calls return 200 OK but push notifications aren't reaching Pixel 10 Pro XL. Device tracker shows `unknown`. The HA Companion app on the phone likely needs to be reopened/reconnected. Code and config are correct — this is a phone-side issue.

---

## Recent Completions (Feb 2026)

**Calendar Check Optimization** — Increased frequency (60→30 min), compressed prompt (322→70 tokens), achieved 57% daily token savings while improving responsiveness.

**ICS Calendar Support** — Added local ICS file calendar reading alongside Google Calendar for flexible scheduling.

**Configurable Job Times** — All scheduled jobs now configurable via .env with validation and "disabled" keyword support.

**Comprehensive Activity Logging** — All 30+ functions instrumented to log activities in real-time for dashboard updates.

**Bidirectional Person-Memory Relationships** — Implemented proper 1:N schema with auto-linking, manual linking tools, and retroactive linking on person creation.

**Task Management System Phase 1 MVP** — Complete task CRUD, workflow engine, priority scoring, daily briefing integration, web dashboard.

**Refocus as Personal Assistant** — Removed 17 HA device control tools, entity management system, 2,921 lines of code. Consolidated around core functions: memories, tasks, communication.

**Tavily Web Search** — Integrated Tavily API for real-time web search, optional feature with graceful degradation if API key not configured.

---

**Last Updated:** February 17, 2026
