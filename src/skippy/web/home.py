import logging

import psycopg
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def homepage():
    """Serve the Skippy dashboard homepage."""
    return HOMEPAGE_HTML


@router.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Return quick stats for dashboard cards."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get memory stats
                await cur.execute(
                    "SELECT COUNT(*) FROM memories WHERE user_id = 'nolan'"
                )
                total_memories = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM memories WHERE user_id = 'nolan' AND created_at >= NOW() - INTERVAL '7 days'"
                )
                recent_memories = (await cur.fetchone())[0]

                # Get people stats
                await cur.execute("SELECT COUNT(*) FROM people WHERE user_id = 'nolan'")
                total_people = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM people WHERE user_id = 'nolan' AND importance_score >= 50"
                )
                important_people = (await cur.fetchone())[0]

                # Get HA entity stats
                await cur.execute(
                    "SELECT COUNT(*) FROM ha_entities WHERE user_id = 'nolan'"
                )
                total_entities = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*) FROM ha_entities WHERE user_id = 'nolan' AND enabled = true"
                )
                enabled_entities = (await cur.fetchone())[0]

                return {
                    "memories": {"total": total_memories, "recent": recent_memories},
                    "people": {"total": total_people, "important": important_people},
                    "ha_entities": {"total": total_entities, "enabled": enabled_entities},
                }
    except Exception:
        logger.exception("Failed to fetch dashboard stats")
        return {
            "memories": {"total": 0, "recent": 0},
            "people": {"total": 0, "important": 0},
            "ha_entities": {"total": 0, "enabled": 0},
        }


HOMEPAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Skippy Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* Dark theme matching existing pages */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f1117;
            color: #e0e0e0;
            padding: 24px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        /* Header */
        .header {
            text-align: center;
            margin-bottom: 48px;
        }
        .header h1 {
            font-size: 2.5rem;
            color: #7eb8ff;
            margin-bottom: 8px;
        }
        .header p {
            color: #888;
            font-size: 1rem;
        }

        /* Cards Grid */
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-bottom: 48px;
        }

        .card {
            background: #1a1d27;
            border: 1px solid #2a2d37;
            border-radius: 8px;
            padding: 24px;
            text-decoration: none;
            color: inherit;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
        }

        .card:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        .card-icon {
            font-size: 2.5rem;
            margin-bottom: 16px;
        }

        .card h2 {
            font-size: 1.4rem;
            margin-bottom: 8px;
        }

        .card p {
            color: #888;
            font-size: 0.9rem;
            margin-bottom: 16px;
            flex-grow: 1;
        }

        .card-stats {
            margin: 16px 0;
        }

        .stat {
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            font-size: 0.85rem;
        }

        .stat-label { color: #777; }
        .stat-value {
            font-weight: 600;
            color: var(--accent);
        }

        .card-button {
            background: transparent;
            border: 1px solid var(--accent);
            color: var(--accent);
            padding: 10px 20px;
            border-radius: 4px;
            text-align: center;
            font-weight: 500;
            margin-top: 8px;
        }

        /* Accent colors for each card */
        .card.memories { --accent: #7eb8ff; }
        .card.people { --accent: #c792ea; }
        .card.entities { --accent: #89ddff; }

        /* Responsive */
        @media (max-width: 768px) {
            .cards-grid {
                grid-template-columns: 1fr;
            }
            .header h1 {
                font-size: 1.8rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Skippy AI Assistant</h1>
            <p>Your personal AI home automation & life management system</p>
        </div>

        <div class="cards-grid">
            <!-- Semantic Memories Card -->
            <a href="/memories" class="card memories">
                <div class="card-icon">🧠</div>
                <h2>Semantic Memories</h2>
                <p>Long-term memory storage with semantic search and categorization</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Total Memories</span>
                        <span class="stat-value" id="memories-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Added This Week</span>
                        <span class="stat-value" id="memories-recent">-</span>
                    </div>
                </div>
                <div class="card-button">View Memories →</div>
            </a>

            <!-- People Card -->
            <a href="/people" class="card people">
                <div class="card-icon">👥</div>
                <h2>People</h2>
                <p>Contact management with fuzzy deduplication and importance ranking</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Total People</span>
                        <span class="stat-value" id="people-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Important & Active</span>
                        <span class="stat-value" id="people-important">-</span>
                    </div>
                </div>
                <div class="card-button">View People →</div>
            </a>

            <!-- HA Entities Card -->
            <a href="/entities" class="card entities">
                <div class="card-icon">🏠</div>
                <h2>Home Assistant</h2>
                <p>Device management with aliases and natural language control</p>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-label">Total Entities</span>
                        <span class="stat-value" id="entities-total">-</span>
                    </div>
                    <div class="stat">
                        <span class="stat-label">Enabled</span>
                        <span class="stat-value" id="entities-enabled">-</span>
                    </div>
                </div>
                <div class="card-button">View Entities →</div>
            </a>
        </div>
    </div>

    <script>
        // Fetch and display stats
        async function loadStats() {
            try {
                const response = await fetch('/api/dashboard/stats');
                const data = await response.json();

                // Update memories stats
                document.getElementById('memories-total').textContent = data.memories.total;
                document.getElementById('memories-recent').textContent = data.memories.recent;

                // Update people stats
                document.getElementById('people-total').textContent = data.people.total;
                document.getElementById('people-important').textContent = data.people.important;

                // Update HA entities stats
                document.getElementById('entities-total').textContent = data.ha_entities.total;
                document.getElementById('entities-enabled').textContent = data.ha_entities.enabled;
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        // Load stats on page load
        loadStats();

        // Refresh every 30 seconds
        setInterval(loadStats, 30000);
    </script>
</body>
</html>
"""
