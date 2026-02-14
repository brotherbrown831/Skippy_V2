# Skippy V2 Roadmap

> Long-term vision for Skippy — from reactive assistant to proactive, context-aware AI.
> This is a living document. Not everything here will be built at once.

## Current State

What's already working:

- LangGraph agent with ReAct pattern (gpt-4o-mini)
- FastAPI backend with voice webhook + OpenAI-compatible chat endpoint
- PostgreSQL 17 + pgvector semantic memory (store, retrieve, dedup)
- langgraph-checkpoint-postgres for conversation persistence
- Home Assistant voice integration via Wyoming satellites
- Docker Compose deployment with dev hot-reload
- Sarcastic Skippy personality with voice/chat modes

**Immediate next task:** Implement Home Assistant tool functions (entity control, sensor queries, scenes) — the graph is already wired for tools, just needs the implementations in `src/skippy/tools/home_assistant.py`.

---

## Phase 1 — Foundation (Make the Brain Reliable)

### 1. Structured Life Data Layer

Move beyond vector-only memory. Add relational tables for structured facts that must be precise and queryable — not probabilistic.

**Tables to add:**
- People (name, birthday, address, relationship)
- Events (holiday, recurring, one-time)
- Gifts (person, date, item)
- Important dates
- Locations

Keep pgvector for unstructured/conversational memory. Use relational tables for anything that needs exact recall.

**Why first?** Because "What did I get Mike last Christmas?" must never rely on embeddings.

### 2. Task & Reminder Engine

Build a proper scheduler system for core assistant behavior.

**Capabilities:**
- One-time reminders
- Recurring reminders
- Escalating reminders (repeat until acknowledged)
- Timers
- Shopping list as structured tasks

**Requires:**
- Background worker (async task runner)
- Task persistence (database-backed)
- Acknowledgement tracking

**Unlocks:**
- "Remind me in 2 hours"
- "Add milk to shopping list"
- "Remind me every first Monday"

### 3. Notification & Escalation System

Outbound communication channels with priority levels. This is what makes Skippy proactive instead of reactive.

**Priority levels:**
| Level | Action |
|-------|--------|
| Store only | Log it, no notification |
| Push notification | HA mobile app / browser push |
| SMS | Text message for important items |
| Critical | Repeat until acknowledged |

**Requires:**
- Acknowledgement tracking
- Escalation delay logic
- Quiet hours logic

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

### 10. Calendar Deep Integration

Full read/write access to calendar with:
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
