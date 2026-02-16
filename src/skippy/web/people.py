import json
import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter, Body
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


@router.get("/api/people/{person_id}/profile")
async def get_person_profile(person_id: int):
    """Return comprehensive person profile with all related memories."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Fetch person details
                await cur.execute(
                    """
                    SELECT person_id, canonical_name, aliases, relationship, birthday,
                           address, phone, email, notes, importance_score,
                           last_mentioned, mention_count, created_at, updated_at
                    FROM people
                    WHERE person_id = %s AND user_id = %s
                    """,
                    (person_id, "nolan"),
                )
                person_row = await cur.fetchone()

                if not person_row:
                    return {"error": "Person not found"}

                person_cols = [desc.name for desc in cur.description]
                person = dict(zip(person_cols, person_row))

                # Convert datetime objects to ISO strings
                for key in ["last_mentioned", "created_at", "updated_at"]:
                    if person.get(key):
                        person[key] = person[key].isoformat()

                # Fetch related memories
                await cur.execute(
                    """
                    SELECT memory_id, content, category, confidence_score,
                           reinforcement_count, created_at
                    FROM semantic_memories
                    WHERE person_id = %s
                      AND user_id = %s
                      AND status = 'active'
                    ORDER BY
                        CASE
                            WHEN category = 'person' THEN 1
                            WHEN category = 'family' THEN 2
                            ELSE 3
                        END,
                        confidence_score DESC,
                        created_at DESC
                    LIMIT 50
                    """,
                    (person_id, "nolan"),
                )
                memory_rows = await cur.fetchall()
                memory_cols = [desc.name for desc in cur.description]

                memories = []
                for row in memory_rows:
                    mem = dict(zip(memory_cols, row))
                    if mem.get("created_at"):
                        mem["created_at"] = mem["created_at"].isoformat()
                    memories.append(mem)

                return {"person": person, "memories": memories}

    except Exception:
        logger.exception("Failed to fetch person profile for ID %s", person_id)
        return {"error": "Database error"}


@router.put("/api/people/{person_id}")
async def update_person_api(person_id: int, data: dict = Body(...)):
    """Update a person's contact information."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Fetch current person
                await cur.execute(
                    """SELECT person_id, aliases
                       FROM people
                       WHERE person_id = %s AND user_id = %s""",
                    (person_id, "nolan"),
                )
                row = await cur.fetchone()
                if not row:
                    return {"ok": False, "error": "Person not found"}

                current_aliases = row[1] or []

                # Build dynamic UPDATE query for contact fields
                sets = []
                params = []

                if "phone" in data:
                    sets.append("phone = %s")
                    params.append(data.get("phone", "").strip() or None)

                if "email" in data:
                    sets.append("email = %s")
                    params.append(data.get("email", "").strip() or None)

                if "birthday" in data:
                    sets.append("birthday = %s")
                    params.append(data.get("birthday", "").strip() or None)

                if "address" in data:
                    sets.append("address = %s")
                    params.append(data.get("address", "").strip() or None)

                if "relationship" in data:
                    sets.append("relationship = %s")
                    params.append(data.get("relationship", "").strip() or None)

                # Update aliases if provided
                if "aliases" in data:
                    sets.append("aliases = %s::jsonb")
                    params.append(json.dumps(data.get("aliases", [])))

                # Always update timestamp
                sets.append("updated_at = NOW()")

                # Execute update if there are fields to update
                if sets:
                    params.append(person_id)
                    params.append("nolan")

                    await cur.execute(
                        f"""
                        UPDATE people SET {", ".join(sets)}
                        WHERE person_id = %s AND user_id = %s
                        """,
                        params,
                    )

        return {"ok": True}

    except Exception as e:
        logger.exception("Failed to update person")
        return {"ok": False, "error": str(e)}


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

        /* Profile Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.4);
            align-items: center;
            justify-content: center;
        }

        .profile-modal-content {
            background-color: white;
            max-width: 900px;
            width: 95%;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
            max-height: 90vh;
        }

        .modal-header {
            padding: 20px;
            border-bottom: 2px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-header h3 {
            margin: 0;
            color: #333;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 28px;
            font-weight: bold;
            color: #666;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .modal-close:hover {
            color: #000;
        }

        .modal-body {
            flex: 1;
            overflow-y: auto;
            padding: 0;
        }

        .profile-grid {
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 0;
            min-height: 400px;
        }

        @media (max-width: 768px) {
            .profile-grid {
                grid-template-columns: 1fr;
            }
        }

        .profile-details {
            padding: 20px;
            border-right: 1px solid #ddd;
            background: #fafafa;
            overflow-y: auto;
            max-height: 60vh;
        }

        @media (max-width: 768px) {
            .profile-details {
                border-right: none;
                border-bottom: 1px solid #ddd;
                max-height: none;
            }
        }

        .profile-details h4 {
            margin: 0 0 15px 0;
            color: #333;
            font-size: 0.95em;
            font-weight: 600;
        }

        .profile-field {
            margin-bottom: 15px;
        }

        .profile-field label {
            display: block;
            font-size: 0.8rem;
            color: #666;
            margin-bottom: 4px;
            font-weight: 500;
        }

        .profile-value {
            color: #333;
            font-size: 0.95rem;
            word-wrap: break-word;
            word-break: break-word;
        }

        .profile-value a {
            color: #2196F3;
            text-decoration: none;
        }

        .profile-value a:hover {
            text-decoration: underline;
        }

        /* Edit mode input styling */
        .profile-input {
            width: 100%;
            padding: 6px 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.95rem;
            font-family: inherit;
            background: white;
        }

        .profile-input:focus {
            outline: none;
            border-color: #2196F3;
            box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.1);
        }

        textarea.profile-input {
            resize: vertical;
            min-height: 40px;
        }

        /* Edit mode toggle */
        .edit-mode .profile-value {
            display: none !important;
        }

        .edit-mode .profile-input {
            display: block !important;
        }

        /* Dark mode support */
        [data-theme="dark"] .profile-input {
            background: #2d2d2d;
            border-color: #444;
            color: #e0e0e0;
        }

        [data-theme="dark"] .profile-input:focus {
            border-color: #2196F3;
        }

        .profile-memories {
            padding: 20px;
            overflow-y: auto;
            max-height: 60vh;
        }

        .profile-memories h4 {
            margin: 0 0 15px 0;
            color: #333;
            font-size: 0.95em;
            font-weight: 600;
        }

        .memories-list {
            margin-top: 10px;
        }

        .memory-card {
            background: #f9f9f9;
            border-left: 4px solid #2196F3;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 4px;
        }

        .memory-card.category-person {
            border-left-color: #4CAF50;
        }

        .memory-card.category-family {
            border-left-color: #FF9800;
        }

        .memory-content {
            color: #333;
            margin-bottom: 6px;
            line-height: 1.5;
            word-wrap: break-word;
            word-break: break-word;
        }

        .memory-meta {
            font-size: 0.8rem;
            color: #888;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .memory-meta span {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .empty-state {
            text-align: center;
            color: #999;
            padding: 40px 20px;
            font-size: 0.9rem;
        }

        /* Clickable person names */
        .person-name-link {
            cursor: pointer;
            color: inherit;
            transition: color 0.2s;
        }

        .person-name-link:hover {
            color: #2196F3;
            text-decoration: underline;
        }

        .modal-footer {
            padding: 15px 20px;
            border-top: 2px solid #ddd;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }

        .btn-cancel {
            background: #e0e0e0;
            color: #333;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }

        .btn-cancel:hover {
            background: #d0d0d0;
        }

        .btn-primary {
            background: #2196F3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }

        .btn-primary:hover:not(:disabled) {
            background: #0b7dda;
        }

        .btn-primary:disabled {
            background: #ccc;
            cursor: not-allowed;
            opacity: 0.6;
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

    <!-- Person Profile Modal -->
    <div id="person-profile-modal" class="modal" style="display: none;">
        <div class="profile-modal-content">
            <div class="modal-header">
                <h3 id="profile-person-name">Person Profile</h3>
                <button class="modal-close" onclick="closePersonProfile()">×</button>
            </div>
            <div class="modal-body">
                <div class="profile-grid">
                    <!-- Left column: Person details -->
                    <div class="profile-details">
                        <h4>Contact Information</h4>
                        <div class="profile-field">
                            <label>Phone</label>
                            <div id="profile-phone" class="profile-value">-</div>
                            <input type="tel" id="profile-phone-edit" class="profile-input" style="display: none;">
                        </div>
                        <div class="profile-field">
                            <label>Email</label>
                            <div id="profile-email" class="profile-value">-</div>
                            <input type="email" id="profile-email-edit" class="profile-input" style="display: none;">
                        </div>
                        <div class="profile-field">
                            <label>Birthday</label>
                            <div id="profile-birthday" class="profile-value">-</div>
                            <input type="date" id="profile-birthday-edit" class="profile-input" style="display: none;">
                        </div>
                        <div class="profile-field">
                            <label>Address</label>
                            <div id="profile-address" class="profile-value">-</div>
                            <textarea id="profile-address-edit" class="profile-input" rows="2" style="display: none;"></textarea>
                        </div>
                        <div class="profile-field">
                            <label>Relationship</label>
                            <div id="profile-relationship" class="profile-value">-</div>
                            <input type="text" id="profile-relationship-edit" class="profile-input" style="display: none;">
                        </div>
                        <div class="profile-field">
                            <label>Aliases</label>
                            <div id="profile-aliases" class="profile-value">-</div>
                            <input type="text" id="profile-aliases-edit" class="profile-input" placeholder="Comma-separated" style="display: none;">
                        </div>

                        <h4 style="margin-top: 20px;">Metadata</h4>
                        <div class="profile-field">
                            <label>Importance Score</label>
                            <div id="profile-importance" class="profile-value">-</div>
                        </div>
                        <div class="profile-field">
                            <label>Mentions</label>
                            <div id="profile-mentions" class="profile-value">-</div>
                        </div>
                        <div class="profile-field">
                            <label>Last Mentioned</label>
                            <div id="profile-last-mentioned" class="profile-value">-</div>
                        </div>
                        <div class="profile-field">
                            <label>Created</label>
                            <div id="profile-created" class="profile-value">-</div>
                        </div>
                    </div>

                    <!-- Right column: Memories -->
                    <div class="profile-memories">
                        <h4>Related Memories (<span id="memories-count">0</span>)</h4>
                        <div id="memories-list" class="memories-list">
                            <div class="empty-state">Loading memories...</div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closePersonProfile()">Close</button>
                <button id="btn-edit" class="btn-primary" onclick="enterEditMode()">Edit</button>
                <button id="btn-save" class="btn-primary" onclick="savePersonProfile()" style="display: none;">Save</button>
                <button id="btn-cancel-edit" class="btn-cancel" onclick="cancelEditMode()" style="display: none;">Cancel</button>
            </div>
        </div>
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
                    (p.last_mentioned && new Date(p.last_mentioned) > new Date(Date.now() - 7*24*60*60*1000))))
                    .sort((a, b) => (b.importance_score || 0) - (a.importance_score || 0))
                    .slice(0, 10);

                // Render important people
                if (important.length > 0) {
                    importantSection.style.display = 'block';
                    importantGrid.innerHTML = important.map(p => `
                        <div class="person-card">
                            <h3>
                                <span class="person-name-link" onclick="openPersonProfile(${p.person_id})">
                                    ${p.canonical_name}
                                </span>
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
                        <td><span class="person-name-link" onclick="openPersonProfile(${p.person_id})"><strong>${p.canonical_name}</strong></span></td>
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

        // Global variable to store current profile data
        let currentPersonProfile = null;

        async function openPersonProfile(personId) {
            try {
                // Show modal with loading state
                const modal = document.getElementById('person-profile-modal');
                modal.style.display = 'flex';

                document.getElementById('profile-person-name').textContent = 'Loading...';
                document.getElementById('memories-list').innerHTML = '<div class="empty-state">Loading memories...</div>';

                // Fetch profile data
                const response = await fetch('/api/people/' + personId + '/profile');
                const data = await response.json();

                if (data.error) {
                    alert('Error: ' + data.error);
                    closePersonProfile();
                    return;
                }

                currentPersonProfile = data;
                renderPersonProfile(data);

            } catch (error) {
                console.error('Error loading person profile:', error);
                alert('Failed to load person profile');
                closePersonProfile();
            }
        }

        function closePersonProfile() {
            document.getElementById('person-profile-modal').style.display = 'none';
            currentPersonProfile = null;
            if (isEditMode) {
                cancelEditMode();
            }
        }

        function renderPersonProfile(data) {
            const person = data.person;
            const memories = data.memories;

            // Header
            document.getElementById('profile-person-name').textContent = person.canonical_name || 'Unknown';

            // Person details
            document.getElementById('profile-phone').innerHTML = person.phone
                ? `<a href="tel:${person.phone}">${person.phone}</a>`
                : '-';

            document.getElementById('profile-email').innerHTML = person.email
                ? `<a href="mailto:${person.email}">${person.email}</a>`
                : '-';

            document.getElementById('profile-birthday').textContent = person.birthday || '-';
            document.getElementById('profile-address').textContent = person.address || '-';
            document.getElementById('profile-relationship').textContent = person.relationship || '-';

            // Aliases
            const aliases = person.aliases || [];
            document.getElementById('profile-aliases').textContent = aliases.length > 0
                ? aliases.join(', ')
                : '-';

            // Metadata
            document.getElementById('profile-importance').innerHTML = person.importance_score
                ? `<span style="color: ${person.importance_score >= 50 ? '#ff9800' : '#666'}">${Math.round(person.importance_score)}</span>`
                : '-';

            document.getElementById('profile-mentions').textContent = person.mention_count || '0';
            document.getElementById('profile-last-mentioned').textContent = formatDate(person.last_mentioned);
            document.getElementById('profile-created').textContent = formatDate(person.created_at);

            // Memories
            document.getElementById('memories-count').textContent = memories.length;

            if (memories.length === 0) {
                document.getElementById('memories-list').innerHTML = '<div class="empty-state">No memories found for this person</div>';
            } else {
                const memoriesHtml = memories.map(mem => {
                    // Category emoji
                    let emoji = '📝';
                    if (mem.category === 'person') emoji = '👤';
                    else if (mem.category === 'family') emoji = '👨‍👩‍👧‍👦';

                    // Confidence badge
                    const confidence = Math.round((mem.confidence_score || 0) * 100);
                    const confBadge = confidence >= 80
                        ? `<span style="color: #4CAF50">${confidence}% conf.</span>`
                        : `<span style="color: #666">${confidence}% conf.</span>`;

                    return `
                        <div class="memory-card category-${mem.category || 'other'}">
                            <div class="memory-content">${emoji} ${mem.content}</div>
                            <div class="memory-meta">
                                <span>Category: ${mem.category || 'fact'}</span>
                                <span>${confBadge}</span>
                                ${mem.reinforcement_count > 0 ? `<span>Reinforced ${mem.reinforcement_count}x</span>` : ''}
                                <span>${formatDate(mem.created_at)}</span>
                            </div>
                        </div>
                    `;
                }).join('');

                document.getElementById('memories-list').innerHTML = memoriesHtml;
            }
        }

        // Edit mode state
        let isEditMode = false;

        function enterEditMode() {
            isEditMode = true;

            // Toggle buttons
            document.getElementById('btn-edit').style.display = 'none';
            document.getElementById('btn-save').style.display = 'inline-block';
            document.getElementById('btn-cancel-edit').style.display = 'inline-block';

            // Populate edit fields with current values
            const person = currentPersonProfile.person;
            document.getElementById('profile-phone-edit').value = person.phone || '';
            document.getElementById('profile-email-edit').value = person.email || '';
            document.getElementById('profile-birthday-edit').value = formatBirthdayForInput(person.birthday);
            document.getElementById('profile-address-edit').value = person.address || '';
            document.getElementById('profile-relationship-edit').value = person.relationship || '';
            document.getElementById('profile-aliases-edit').value = (person.aliases || []).join(', ');

            // Add edit mode class to show inputs, hide values
            document.querySelector('.profile-details').classList.add('edit-mode');
        }

        function cancelEditMode() {
            isEditMode = false;

            // Reset buttons
            document.getElementById('btn-edit').style.display = 'inline-block';
            document.getElementById('btn-save').style.display = 'none';
            document.getElementById('btn-cancel-edit').style.display = 'none';

            // Remove edit mode class
            document.querySelector('.profile-details').classList.remove('edit-mode');
        }

        async function savePersonProfile() {
            try {
                const personId = currentPersonProfile.person.person_id;

                // Gather edited values
                const updates = {
                    phone: document.getElementById('profile-phone-edit').value.trim(),
                    email: document.getElementById('profile-email-edit').value.trim(),
                    birthday: document.getElementById('profile-birthday-edit').value.trim(),
                    address: document.getElementById('profile-address-edit').value.trim(),
                    relationship: document.getElementById('profile-relationship-edit').value.trim(),
                    aliases: document.getElementById('profile-aliases-edit').value
                        .split(',')
                        .map(a => a.trim())
                        .filter(a => a.length > 0)
                };

                // Send PUT request
                const response = await fetch(`/api/people/${personId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updates)
                });

                const result = await response.json();

                if (result.ok) {
                    // Refresh profile data
                    const profileResponse = await fetch(`/api/people/${personId}/profile`);
                    const newData = await profileResponse.json();
                    currentPersonProfile = newData;
                    renderPersonProfile(newData);

                    // Exit edit mode
                    cancelEditMode();

                    // Refresh main people list
                    loadPeople();
                } else {
                    alert('Error saving: ' + (result.error || 'Unknown error'));
                }

            } catch (error) {
                console.error('Error saving person profile:', error);
                alert('Failed to save changes. Please try again.');
            }
        }

        function formatBirthdayForInput(birthday) {
            if (!birthday) return '';

            // If already in YYYY-MM-DD format, return as-is
            if (/^\d{4}-\d{2}-\d{2}$/.test(birthday)) {
                return birthday;
            }

            // If MM-DD format, prepend a placeholder year (2000)
            if (/^\d{2}-\d{2}$/.test(birthday)) {
                return `2000-${birthday}`;
            }

            return birthday;
        }

        // Load people on page load
        loadPeople();
        // Refresh every 30 seconds
        setInterval(loadPeople, 30000);
    </script>
</body>
</html>
"""
