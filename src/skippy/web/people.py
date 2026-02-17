import json
import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse, RedirectResponse

from skippy.config import settings
from .shared_ui import render_html_page, render_page_header, render_section

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
                await cur.execute("""
                    SELECT
                        person_id, canonical_name, relationship, phone, email,
                        importance_score, last_mentioned,
                        (SELECT COUNT(*) FROM semantic_memories WHERE person_id = people.person_id) as memory_count
                    FROM people
                    WHERE canonical_name IS NOT NULL AND canonical_name != ''
                    ORDER BY importance_score DESC
                """)
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]
                people = [dict(zip(columns, row)) for row in rows]
                return people
    except Exception as e:
        logger.error(f"Failed to get people: {e}")
        return []


@router.delete("/api/people/{person_id}")
async def delete_person(person_id: int):
    """Delete a person."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM people WHERE person_id = %s", (person_id,))
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to delete person: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/api/people/{person_id}/profile")
async def get_person_profile(person_id: int):
    """Get detailed person profile with memories."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Get person details
                await cur.execute("""
                    SELECT person_id, canonical_name, aliases, relationship, phone, email,
                           importance_score, last_mentioned, notes
                    FROM people
                    WHERE person_id = %s
                """, (person_id,))
                row = await cur.fetchone()
                if not row:
                    return {"error": "Person not found"}

                person = dict(zip([desc.name for desc in cur.description], row))

                # Parse aliases JSON
                if person.get('aliases'):
                    try:
                        person['aliases'] = json.loads(person['aliases'])
                    except:
                        person['aliases'] = []

                # Get memories
                await cur.execute("""
                    SELECT memory_id, content, confidence_score, created_at
                    FROM semantic_memories
                    WHERE person_id = %s
                    ORDER BY created_at DESC
                    LIMIT 50
                """, (person_id,))
                memories = [
                    dict(zip([desc.name for desc in cur.description], m))
                    for m in await cur.fetchall()
                ]

                person['memories'] = memories
                return person

    except Exception as e:
        logger.error(f"Failed to get person profile: {e}")
        return {"error": str(e)}


@router.put("/api/people/{person_id}")
async def update_person(person_id: int, data: dict = Body(...)):
    """Update person details."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                updates = []
                values = []

                if "relationship" in data:
                    updates.append("relationship = %s")
                    values.append(data["relationship"])
                if "phone" in data:
                    updates.append("phone = %s")
                    values.append(data["phone"])
                if "email" in data:
                    updates.append("email = %s")
                    values.append(data["email"])
                if "notes" in data:
                    updates.append("notes = %s")
                    values.append(data["notes"])

                if not updates:
                    return {"ok": False, "error": "No valid fields to update"}

                values.append(person_id)
                query = f"UPDATE people SET {', '.join(updates)} WHERE person_id = %s"
                await cur.execute(query, values)

        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to update person: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/api/people")
async def create_person(data: dict = Body(...)):
    """Create a new person."""
    try:
        canonical_name = data.get("name", "").strip()
        if not canonical_name:
            return {"ok": False, "error": "Name is required"}

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO people (canonical_name, relationship, phone, email, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING person_id
                    """,
                    (
                        canonical_name,
                        data.get("relationship"),
                        data.get("phone"),
                        data.get("email"),
                    ),
                )
                result = await cur.fetchone()
                person_id = result[0] if result else None

        return {"ok": True, "person_id": person_id}
    except Exception as e:
        logger.error(f"Failed to create person: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/people", response_class=HTMLResponse)
async def people_page():
    """Serve the people management page."""
    return PEOPLE_PAGE_HTML


def get_people_html() -> str:
    """Generate people page using shared design system."""

    page_content = render_page_header(
        "👥 People",
        "Manage your important contacts and relationships"
    )

    # Controls
    controls_html = '''
        <div class="page-controls">
            <button class="btn btn-primary" onclick="openAddPersonModal()" style="margin-right: var(--spacing-8);">+ Add Person</button>
            <input type="text" id="search-input" placeholder="Search people..." style="flex: 1; max-width: 300px; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    # Important people section
    important_html = '''
        <div id="important-section" style="margin-bottom: var(--spacing-16); display: none;">
            <div style="color: var(--accent-blue); font-weight: 600; margin-bottom: var(--spacing-12); font-size: 0.95rem;">⭐ IMPORTANT & ACTIVE</div>
            <div id="important-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: var(--spacing-12);"></div>
        </div>'''

    # All people table
    people_html = '''
        <table style="width: 100%; border-collapse: collapse; margin-top: var(--spacing-12);">
            <thead>
                <tr>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Name</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Relationship</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Phone</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Email</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Memories</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Score</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Last Mentioned</th>
                    <th style="background: var(--bg-tertiary); color: var(--accent-blue); padding: var(--spacing-8); text-align: left; border-bottom: 1px solid var(--border-color); font-weight: 600;">Actions</th>
                </tr>
            </thead>
            <tbody id="people-body"></tbody>
        </table>'''

    page_content += controls_html
    page_content += render_section("", important_html)
    page_content += render_section("All People", people_html)

    # Modals
    modals_html = '''
        <!-- Add Person Modal -->
        <div id="add-person-modal" class="modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.6); align-items: center; justify-content: center;">
            <div class="modal-content" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: var(--spacing-16); max-width: 500px; width: 90%;">
                <h2 style="color: var(--accent-blue); margin-bottom: var(--spacing-12); font-size: 1.4rem;">Add New Person</h2>
                <form onsubmit="submitAddPerson(event)">
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Name *</label>
                        <input type="text" id="add-person-name" required style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Relationship</label>
                        <input type="text" id="add-person-relationship" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Phone</label>
                        <input type="tel" id="add-person-phone" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="margin-bottom: var(--spacing-12);">
                        <label style="display: block; color: var(--text-main); font-weight: 500; margin-bottom: var(--spacing-4);">Email</label>
                        <input type="email" id="add-person-email" style="width: 100%; padding: var(--spacing-8); background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); font-size: 0.9rem;">
                    </div>
                    <div style="display: flex; gap: var(--spacing-8); justify-content: flex-end;">
                        <button type="button" class="btn btn-ghost" onclick="closeAddPersonModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Add Person</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- Person Profile Modal -->
        <div id="person-profile-modal" class="modal" style="display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.6); align-items: center; justify-content: center; overflow-y: auto;">
            <div class="modal-content" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-lg); padding: var(--spacing-16); max-width: 600px; width: 90%; margin: var(--spacing-16) auto;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--spacing-12);">
                    <h2 id="profile-person-name" style="color: var(--accent-blue); font-size: 1.4rem; margin: 0;">Loading...</h2>
                    <button onclick="closePersonProfile()" style="background: none; border: none; font-size: 1.5rem; color: var(--text-muted); cursor: pointer;">✕</button>
                </div>

                <div id="profile-content" style="display: none;">
                    <div style="background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-12); margin-bottom: var(--spacing-12);">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-8); margin-bottom: var(--spacing-12);">
                            <div>
                                <label style="display: block; color: var(--text-muted); font-size: 0.85rem; margin-bottom: var(--spacing-4);">Relationship</label>
                                <span id="profile-relationship" style="color: var(--text-main);">-</span>
                            </div>
                            <div>
                                <label style="display: block; color: var(--text-muted); font-size: 0.85rem; margin-bottom: var(--spacing-4);">Phone</label>
                                <span id="profile-phone" style="color: var(--text-main);">-</span>
                            </div>
                            <div>
                                <label style="display: block; color: var(--text-muted); font-size: 0.85rem; margin-bottom: var(--spacing-4);">Email</label>
                                <span id="profile-email" style="color: var(--text-main);">-</span>
                            </div>
                            <div>
                                <label style="display: block; color: var(--text-muted); font-size: 0.85rem; margin-bottom: var(--spacing-4);">Importance</label>
                                <span id="profile-importance" style="color: var(--text-main);">-</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary" onclick="enableEditMode()" style="width: 100%; margin-bottom: var(--spacing-8);">✎ Edit</button>
                        <div id="edit-mode" style="display: none;">
                            <input type="text" id="edit-relationship" style="width: 100%; padding: var(--spacing-8); background: var(--bg-main); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); margin-bottom: var(--spacing-8);" placeholder="Relationship">
                            <input type="tel" id="edit-phone" style="width: 100%; padding: var(--spacing-8); background: var(--bg-main); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); margin-bottom: var(--spacing-8);" placeholder="Phone">
                            <input type="email" id="edit-email" style="width: 100%; padding: var(--spacing-8); background: var(--bg-main); border: 1px solid var(--border-color); border-radius: var(--radius-md); color: var(--text-main); margin-bottom: var(--spacing-8);" placeholder="Email">
                            <div style="display: flex; gap: var(--spacing-8);">
                                <button type="button" class="btn btn-primary" onclick="savePersonChanges()" style="flex: 1;">Save</button>
                                <button type="button" class="btn btn-ghost" onclick="cancelEditMode()" style="flex: 1;">Cancel</button>
                            </div>
                        </div>
                    </div>

                    <div style="margin-bottom: var(--spacing-12);">
                        <h3 style="color: var(--accent-blue); font-size: 1.1rem; margin-bottom: var(--spacing-8);">📝 Memories</h3>
                        <div id="memories-list"></div>
                    </div>
                </div>
            </div>
        </div>
    '''

    scripts = '''
    <script>
        let currentPersonProfile = null;
        let isEditMode = false;

        function formatDate(dateStr) {
            if (!dateStr) return '-';
            const d = new Date(dateStr);
            return d.toLocaleDateString();
        }

        async function loadPeople(searchQuery = '') {
            try {
                const response = await fetch('/api/people');
                const people = await response.json();
                const tbody = document.getElementById('people-body');
                const importantSection = document.getElementById('important-section');
                const importantGrid = document.getElementById('important-grid');

                if (!people || people.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">No people found</td></tr>';
                    return;
                }

                // Filter if search query
                let filtered = people;
                if (searchQuery) {
                    filtered = people.filter(p =>
                        p.canonical_name.toLowerCase().includes(searchQuery.toLowerCase())
                    );
                }

                // Separate important and all people
                const important = filtered.filter(p =>
                    (p.canonical_name && p.canonical_name.trim() !== '') &&
                    (p.importance_score >= 50 ||
                    (p.last_mentioned && new Date(p.last_mentioned) > new Date(Date.now() - 7*24*60*60*1000))))
                    .sort((a, b) => (b.importance_score || 0) - (a.importance_score || 0))
                    .slice(0, 10);

                // Render important people
                if (important.length > 0) {
                    importantSection.style.display = 'block';
                    importantGrid.innerHTML = important.map(p => `
                        <div style="background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-12); cursor: pointer; transition: all 0.2s;" onmouseover="this.style.borderColor='var(--accent-blue)'" onmouseout="this.style.borderColor='var(--border-color)'">
                            <h3 style="color: var(--text-main); margin: 0 0 var(--spacing-8) 0; font-size: 1rem;">
                                <span onclick="openPersonProfile(${p.person_id})" style="cursor: pointer; color: var(--accent-blue);">
                                    ${p.canonical_name}
                                </span>
                                <span style="color: var(--accent-purple); float: right; font-size: 0.9rem;">${Math.round(p.importance_score || 0)}</span>
                            </h3>
                            ${p.relationship ? '<div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: var(--spacing-4);">' + p.relationship + '</div>' : ''}
                            <div style="color: var(--text-muted); font-size: 0.85rem;">Last: ${formatDate(p.last_mentioned)}</div>
                        </div>
                    `).join('');
                }

                // Render all people
                tbody.innerHTML = filtered.map(p => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: var(--spacing-8); color: var(--text-main); cursor: pointer;" onclick="openPersonProfile(${p.person_id})"><strong style="color: var(--accent-blue);">${p.canonical_name}</strong></td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${p.relationship || '-'}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${p.phone || '-'}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${p.email || '-'}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${p.memory_count || 0} facts</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${Math.round(p.importance_score || 0)}</td>
                        <td style="padding: var(--spacing-8); color: var(--text-main);">${formatDate(p.last_mentioned)}</td>
                        <td style="padding: var(--spacing-8);"><button class="btn btn-danger" onclick="deletePerson(${p.person_id})" style="padding: 4px 12px; font-size: 0.85rem;">Delete</button></td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('Error loading people:', error);
                document.getElementById('people-body').innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">Error loading people</td></tr>';
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

        async function openPersonProfile(personId) {
            try {
                const modal = document.getElementById('person-profile-modal');
                modal.style.display = 'flex';

                document.getElementById('profile-person-name').textContent = 'Loading...';
                document.getElementById('profile-content').style.display = 'none';

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

        function renderPersonProfile(data) {
            document.getElementById('profile-person-name').textContent = data.canonical_name;
            document.getElementById('profile-relationship').textContent = data.relationship || '-';
            document.getElementById('profile-phone').textContent = data.phone || '-';
            document.getElementById('profile-email').textContent = data.email || '-';
            document.getElementById('profile-importance').textContent = Math.round(data.importance_score || 0);

            const memoriesList = document.getElementById('memories-list');
            if (data.memories && data.memories.length > 0) {
                memoriesList.innerHTML = data.memories.map(m => `
                    <div style="background: var(--bg-main); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-8); margin-bottom: var(--spacing-8);">
                        <div style="color: var(--text-main); font-size: 0.9rem; margin-bottom: var(--spacing-4);">${m.content}</div>
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: var(--text-muted); font-size: 0.8rem;">Score: ${Math.round(m.confidence_score || 0)}</span>
                            <span style="color: var(--text-muted); font-size: 0.8rem;">${formatDate(m.created_at)}</span>
                        </div>
                    </div>
                `).join('');
            } else {
                memoriesList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: var(--spacing-12);">No memories recorded</div>';
            }

            document.getElementById('profile-content').style.display = 'block';
            isEditMode = false;
            document.getElementById('edit-mode').style.display = 'none';
        }

        function closePersonProfile() {
            document.getElementById('person-profile-modal').style.display = 'none';
            currentPersonProfile = null;
            isEditMode = false;
        }

        function enableEditMode() {
            isEditMode = true;
            const data = currentPersonProfile;
            document.getElementById('edit-relationship').value = data.relationship || '';
            document.getElementById('edit-phone').value = data.phone || '';
            document.getElementById('edit-email').value = data.email || '';
            document.getElementById('edit-mode').style.display = 'block';
        }

        function cancelEditMode() {
            isEditMode = false;
            document.getElementById('edit-mode').style.display = 'none';
        }

        async function savePersonChanges() {
            const relationship = document.getElementById('edit-relationship').value;
            const phone = document.getElementById('edit-phone').value;
            const email = document.getElementById('edit-email').value;

            try {
                const response = await fetch('/api/people/' + currentPersonProfile.person_id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ relationship, phone, email })
                });
                const result = await response.json();
                if (result.ok) {
                    currentPersonProfile.relationship = relationship;
                    currentPersonProfile.phone = phone;
                    currentPersonProfile.email = email;
                    renderPersonProfile(currentPersonProfile);
                    loadPeople();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error updating person: ' + error);
            }
        }

        function openAddPersonModal() {
            document.getElementById('add-person-modal').style.display = 'flex';
            document.getElementById('add-person-name').focus();
        }

        function closeAddPersonModal() {
            document.getElementById('add-person-modal').style.display = 'none';
            document.getElementById('add-person-name').value = '';
            document.getElementById('add-person-relationship').value = '';
            document.getElementById('add-person-phone').value = '';
            document.getElementById('add-person-email').value = '';
        }

        async function submitAddPerson(e) {
            e.preventDefault();
            const name = document.getElementById('add-person-name').value;
            const relationship = document.getElementById('add-person-relationship').value;
            const phone = document.getElementById('add-person-phone').value;
            const email = document.getElementById('add-person-email').value;

            try {
                const response = await fetch('/api/people', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, relationship, phone, email })
                });
                const result = await response.json();
                if (result.ok) {
                    closeAddPersonModal();
                    loadPeople();
                } else {
                    alert('Error: ' + result.error);
                }
            } catch (error) {
                alert('Error creating person: ' + error);
            }
        }

        // Search
        document.getElementById('search-input').addEventListener('input', (e) => {
            loadPeople(e.target.value);
        });

        // Close modals on outside click
        window.onclick = (event) => {
            const addModal = document.getElementById('add-person-modal');
            const profileModal = document.getElementById('person-profile-modal');
            if (event.target === addModal) {
                closeAddPersonModal();
            }
            if (event.target === profileModal) {
                closePersonProfile();
            }
        };

        // Initial load
        loadPeople();
    </script>
    '''

    full_html = page_content + modals_html + scripts
    return render_html_page("People", full_html)


PEOPLE_PAGE_HTML = get_people_html()
