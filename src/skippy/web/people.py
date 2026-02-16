import json
import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/api/people")
async def get_people():
    """Return all people as JSON."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT p.person_id, p.canonical_name, p.aliases, p.relationship, p.birthday,
                           p.address, p.phone, p.email, p.notes, p.importance_score,
                           p.last_mentioned, p.mention_count, p.created_at, p.updated_at,
                           COUNT(m.memory_id) AS memory_count
                    FROM people p
                    LEFT JOIN semantic_memories m ON p.person_id = m.person_id AND m.status = 'active'
                    WHERE p.user_id = %s
                    GROUP BY p.person_id
                    ORDER BY p.canonical_name;
                    """,
                    ("nolan",),
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                return [
                    {
                        col: (
                            val.isoformat()
                            if isinstance(val, datetime)
                            else val
                        )
                        for col, val in zip(columns, row)
                    }
                    for row in rows
                ]
    except Exception:
        logger.exception("Failed to fetch people")
        return []


@router.get("/api/people/important")
async def get_important_people():
    """Return important and recently mentioned people."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases, relationship,
                           importance_score, last_mentioned, mention_count
                    FROM people
                    WHERE user_id = %s
                      AND (importance_score >= 50 OR last_mentioned >= NOW() - INTERVAL '7 days')
                    ORDER BY importance_score DESC, last_mentioned DESC
                    LIMIT 10;
                    """,
                    ("nolan",),
                )
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                return [
                    {
                        col: (
                            val.isoformat()
                            if isinstance(val, datetime)
                            else val
                        )
                        for col, val in zip(columns, row)
                    }
                    for row in rows
                ]
    except Exception:
        logger.exception("Failed to fetch important people")
        return []


@router.get("/api/people/duplicates")
async def get_duplicate_clusters():
    """Return potential duplicate person clusters."""
    try:
        from skippy.tools.people import find_duplicate_people

        result = await find_duplicate_people()
        try:
            # find_duplicate_people returns JSON string
            clusters = json.loads(result) if isinstance(result, str) else result
            return clusters if isinstance(clusters, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    except Exception:
        logger.exception("Failed to find duplicate people")
        return []


@router.delete("/api/people/{person_id}")
async def delete_person(person_id: int):
    """Delete a person by ID."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM people WHERE person_id = %s AND user_id = %s",
                    (person_id, "nolan"),
                )
                if cur.rowcount == 0:
                    return {"ok": False, "error": "Person not found"}
                return {"ok": True}
    except Exception:
        logger.exception("Failed to delete person %s", person_id)
        return {"ok": False, "error": "Database error"}


@router.get("/people", response_class=HTMLResponse)
async def people_page():
    """Serve the people viewer page."""
    return PEOPLE_PAGE_HTML


PEOPLE_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>People</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #333; margin-top: 0; }
        h2 { color: #666; border-bottom: 2px solid #ddd; padding-bottom: 10px; }
        .section { margin: 30px 0; }
        .important-section {
            background: #fff8f0;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ff9800;
        }
        .people-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }
        .person-card {
            background: white;
            padding: 15px;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-top: 3px solid #2196F3;
        }
        .person-card h3 {
            margin: 0 0 5px 0;
            color: #333;
        }
        .person-card .importance {
            display: inline-block;
            background: #ff9800;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            margin-left: 5px;
        }
        .person-card .relationship {
            color: #666;
            font-size: 0.9em;
        }
        .person-card .last-mentioned {
            color: #999;
            font-size: 0.85em;
            margin-top: 5px;
        }
        .people-table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .people-table thead {
            background: #f5f5f5;
            font-weight: bold;
            border-bottom: 2px solid #ddd;
        }
        .people-table th, .people-table td {
            padding: 12px 15px;
            text-align: left;
        }
        .people-table tbody tr:hover {
            background: #f9f9f9;
        }
        .people-table tbody tr:nth-child(even) {
            background: #fafafa;
        }
        .delete-btn {
            background: #f44336;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.85em;
        }
        .delete-btn:hover {
            background: #d32f2f;
        }
        .empty {
            text-align: center;
            color: #999;
            padding: 20px;
        }
    </style>
</head>
<body>
    <h1>People</h1>

    <div class="section important-section" id="important-section" style="display:none;">
        <h2>⭐ Important & Active</h2>
        <div class="people-grid" id="important-grid"></div>
    </div>

    <div class="section">
        <h2>All People</h2>
        <table class="people-table" id="people-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Relationship</th>
                    <th>Phone</th>
                    <th>Email</th>
                    <th>Memories</th>
                    <th>Importance</th>
                    <th>Last Mentioned</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="people-body">
                <tr><td colspan="8" class="empty">Loading...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        function formatDate(dateStr) {
            if (!dateStr) return 'Never';
            const date = new Date(dateStr);
            const now = new Date();
            const diffMs = now - date;
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            if (diffDays < 7) return diffDays + ' days ago';
            return date.toLocaleDateString();
        }

        async function loadPeople() {
            try {
                const response = await fetch('/api/people');
                const people = await response.json();

                const tbody = document.getElementById('people-body');
                const importantGrid = document.getElementById('important-grid');
                const importantSection = document.getElementById('important-section');

                if (people.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" class="empty">No people found</td></tr>';
                    return;
                }

                // Separate important and all people
                const important = people.filter(p =>
                    (p.canonical_name && p.canonical_name.trim() !== '') &&
                    (p.importance_score >= 50 ||
                    (p.last_mentioned && new Date(p.last_mentioned) > new Date(Date.now() - 7*24*60*60*1000))));

                // Render important people
                if (important.length > 0) {
                    importantSection.style.display = 'block';
                    importantGrid.innerHTML = important.map(p => `
                        <div class="person-card">
                            <h3>
                                ${p.canonical_name}
                                <span class="importance">${Math.round(p.importance_score || 0)}</span>
                            </h3>
                            ${p.relationship ? '<div class="relationship">' + p.relationship + '</div>' : ''}
                            <div class="last-mentioned">Last: ${formatDate(p.last_mentioned)}</div>
                        </div>
                    `).join('');
                }

                // Render all people
                tbody.innerHTML = people.map(p => `
                    <tr>
                        <td><strong>${p.canonical_name}</strong></td>
                        <td>${p.relationship || '-'}</td>
                        <td>${p.phone || '-'}</td>
                        <td>${p.email || '-'}</td>
                        <td>${p.memory_count || 0} facts</td>
                        <td>${Math.round(p.importance_score || 0)}</td>
                        <td>${formatDate(p.last_mentioned)}</td>
                        <td><button class="delete-btn" onclick="deletePerson(${p.person_id})">Delete</button></td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('Error loading people:', error);
                document.getElementById('people-body').innerHTML = '<tr><td colspan="8" class="empty">Error loading people</td></tr>';
            }
        }

        async function deletePerson(personId) {
            if (!confirm('Are you sure you want to delete this person?')) return;
            try {
                const response = await fetch('/api/people/' + personId, { method: 'DELETE' });
                const result = await response.json();
                if (result.ok) {
                    loadPeople();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error deleting person: ' + error);
            }
        }

        // Load people on page load
        loadPeople();
        // Refresh every 30 seconds
        setInterval(loadPeople, 30000);
    </script>
</body>
</html>
"""
