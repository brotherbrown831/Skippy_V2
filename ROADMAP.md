# Skippy V2 Roadmap

> Long-term vision for Skippy — from reactive assistant to proactive, context-aware AI.
> This is a living document. Not everything here will be built at once.

## Current State

What's already working:

- **LangGraph agent** with ReAct pattern (gpt-4o-mini via Chat Completions for tool execution, Responses API for memory caching)
- FastAPI backend with voice webhook + OpenAI-compatible chat endpoint
- PostgreSQL 17 + pgvector semantic memory (store, retrieve, dedup)
- langgraph-checkpoint-postgres for conversation persistence
- **Home Assistant** voice integration via Wyoming satellites + REST API with fuzzy entity matching (type "office lights" instead of `light.office_lights`)
- **Telegram bot** with long-polling (receive + send messages)
- Docker Compose deployment with dev hot-reload
- Sarcastic Skippy personality with voice/chat/Telegram modes
- Google Calendar integration (read/write via service account)
- Gmail integration (read inbox, search, send, reply via OAuth2)
- Google Contacts integration (search, view, create, update via OAuth2)
- **Google Contacts → People table sync** (daily at 2 AM + on-demand)
- Push notifications via HA Companion app
- SMS notifications via Twilio
- APScheduler task engine (recurring tasks, one-time reminders, timers, direct-function routines)
- Structured people database with auto-extraction + Google Contacts sync
- Unified Memory Bank web dashboard (semantic memories + people)
- **41 tools** across 9 modules

---

## Phase 1 — Foundation (Make the Brain Reliable)

### 1. Structured Life Data Layer ✅

~~Move beyond vector-only memory.~~ Done — `people` table with CRUD tools + auto-extraction from conversations.

**Completed:**
- People table (name, birthday, address, relationship, phone, email, notes)
- 5 CRUD tools (add, get, search, update, list)
- Auto-extraction: memory evaluator detects person/family facts and upserts into people table
- **Google Contacts sync**: daily auto-sync at 2 AM + on-demand `sync_contacts_now` tool (253 contacts imported)
- Unified Memory Bank web dashboard with tabbed view
- **Home Assistant fuzzy entity matching**: All 14 HA device control tools support natural language entity names (multi-tier confidence: 85+ auto-use, 70-84 suggest, <70 reject, 5-min entity cache)

**Remaining:**
- Events table (holiday, recurring, one-time)
- Gifts table (person, date, item)
- Locations table

### 2. Task & Reminder Engine ✅

~~Build a proper scheduler system.~~ Done — APScheduler with database persistence.

**Completed:**
- One-time reminders (`set_reminder` tool)
- Recurring tasks (`create_scheduled_task` tool)
- Timer support (relative delays like "10 minutes")
- Predefined routines (Morning Briefing, Evening Summary, Event Reminder)
- Database-backed task persistence with restore on restart

**Remaining:**
- Escalating reminders (repeat until acknowledged)
- Shopping list as structured tasks

### 3. Notification & Escalation System ✅ (partial)

~~Outbound communication channels.~~ Push + SMS done.

**Completed:**
| Level | Channel | Status |
|-------|---------|--------|
| Push notification | HA Companion app | ✅ Working (phone-side reconnect needed) |
| SMS | Twilio | ✅ Working |
| Telegram | Long-polling bot | ✅ Working |

**Remaining:**
- Acknowledgement tracking
- Escalation delay logic (repeat until acknowledged)
- Quiet hours logic
- Priority-based channel selection (auto-escalate from push → SMS → Telegram)

---

## Phase 2 — Awareness & Monitoring

### 4. Event Ingestion Framework

Standardized way to ingest events from external sources. Everything becomes a normalized event instead of hardcoding each integration.

**Sources:**
- Email
- Home Assistant sensors
- Calendar changes
- Financial alerts
- Camera alerts
- Stock alerts

**Normalized event format:**
```
source: string
type: string
payload: object
timestamp: datetime
confidence: float
```

This enables scaling cleanly — new integrations just emit events in the standard format.

### 5. Priority Scoring Engine

Every incoming event gets scored to determine if and how to notify.

**Scoring factors:**
- Urgency
- Historical sensitivity
- Context (time, calendar state, location)
- Sender importance
- Deviation from normal patterns

If score > threshold, trigger notification at the appropriate priority level (from Phase 1.3).

This is where Skippy becomes intelligent instead of noisy.

### 6. Context Awareness Layer

Add context weighting so the same event can mean different things depending on circumstances.

**Context signals:**
- Time of day
- Meeting status (in a meeting vs. free)
- Driving / home / away
- Sleep hours
- Family member context

**Example:**
- Garage opens at 2AM = critical alert
- Garage opens at 5PM = ignore

---

## Phase 3 — Intelligence Upgrade

### 7. Memory Intelligence 2.0

Enhance the existing semantic memory system with smarter retrieval and lifecycle management.

**Additions:**
- Recency weighting (newer memories rank higher)
- Importance reinforcement (frequently accessed = more important)
- Time decay (old, unused memories fade)
- Category weighting (some categories matter more in certain contexts)
- Cross-memory linking (connect related facts)

Goal: Skippy remembers like a human — recent and important things surface first, old irrelevant things fade.

### 8. Long-Term Relationship Tracking

Build on the structured life data (Phase 1.1) to track relationship patterns over time.

**Track:**
- Last contact date with each person
- Gift history
- Communication patterns

**Enables:**
- "You haven't talked to Mark in 3 months."
- "You bought Hera Legos last year."

**Depends on:** Phase 1.1 (Structured Life Data Layer)

### 9. Reflection & Summary Engine

Periodic self-analysis to increase long-term usefulness.

**Capabilities:**
- Weekly summaries of activity and events
- Missed event analysis
- Behavioral trend detection
- Important recurring signal identification

---

## Phase 4 — Expansion

### 10. Calendar Deep Integration (partially done)

Full read/write access ✅ — 6 calendar tools via service account. Remaining:
- Conflict detection
- Suggestion engine ("You have a gap Tuesday afternoon")
- Auto-scheduling based on priorities

### 11. Tool Registry Abstraction

Formal tool registry instead of manual tool wiring. New tools register themselves with metadata (name, description, parameters, permissions).

**Prepares for:**
- Web search
- Financial APIs
- Smart home integrations beyond HA
- Future tools added without touching the graph

### 12. Admin Dashboard

Observability layer for managing Skippy.

**View and manage:**
- Stored memories (semantic + structured)
- Structured life graph (people, events, gifts)
- Active reminders and tasks
- Event ingestion logs
- Escalation history
- Tool usage stats

---

## Dependency Map

```
HA Tools (now)
    |
Phase 1.1 Structured Data ──────────────────────┐
    |                                             |
Phase 1.2 Task/Reminder Engine                    |
    |                                             |
Phase 1.3 Notification/Escalation                 |
    |                                             |
Phase 2.4 Event Ingestion ───┐                    |
    |                        |                    |
Phase 2.5 Priority Scoring ──┤                    |
    |                        |                    |
Phase 2.6 Context Awareness ─┘                    |
                                                  |
Phase 3.7 Memory 2.0                              |
    |                                             |
Phase 3.8 Relationship Tracking ──────────────────┘
    |
Phase 3.9 Reflection Engine
    |
Phase 4.10-12 Calendar, Tool Registry, Dashboard
```
