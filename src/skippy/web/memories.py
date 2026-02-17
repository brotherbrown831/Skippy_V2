import logging
from datetime import datetime

from skippy.db_utils import get_db_connection
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from skippy.config import settings
from .shared_ui import render_html_page, render_page_header, render_section, render_button

logger = logging.getLogger("skippy")

router = APIRouter()

VALID_SORT_COLUMNS = {
    "created_at",
    "updated_at",
    "confidence_score",
    "reinforcement_count",
    "category",
}


@router.get("/api/memories")
async def get_memories(
    category: str | None = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
):
    """Return all active memories as JSON."""
    if sort not in VALID_SORT_COLUMNS:
        sort = "created_at"
    if order not in ("asc", "desc"):
        order = "desc"

    conditions = ["user_id = %s", "status = 'active'"]
    params: list = ["nolan"]

    if category:
        conditions.append("category = %s")
        params.append(category)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT memory_id, content, category, confidence_score,
               reinforcement_count, status, created_at, updated_at
        FROM semantic_memories
        WHERE {where}
        ORDER BY {sort} {order}
        LIMIT 500;
    """

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
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
        logger.exception("Failed to fetch memories")
        return []


@router.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: int):
    """Delete a memory by ID."""
    sql = "DELETE FROM semantic_memories WHERE memory_id = %s AND user_id = %s"
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (memory_id, "nolan"))
                if cur.rowcount == 0:
                    return {"ok": False, "error": "Memory not found"}
                return {"ok": True}
    except Exception:
        logger.exception("Failed to delete memory %s", memory_id)
        return {"ok": False, "error": "Database error"}


@router.get("/memories", response_class=HTMLResponse)
async def memories_page():
    """Serve the memory viewer page."""
    return MEMORIES_PAGE_HTML


def get_memories_page_html() -> str:
    """Generate the memories page HTML using the shared design system."""

    page_content = render_page_header(
        "🧠 Memories",
        "Search and manage your semantic memories"
    )

    # Navigation controls
    nav_html = '''
        <div class="page-controls">
            <a href="/" class="btn btn-ghost">← Back to Dashboard</a>
        </div>'''

    controls_html = '''
        <div class="page-controls">
            <select id="category">
                <option value="">All Categories</option>
                <option value="family">Family</option>
                <option value="person">Person</option>
                <option value="preference">Preference</option>
                <option value="project">Project</option>
                <option value="technical">Technical</option>
                <option value="event">Event</option>
                <option value="recurring_event">Recurring Event</option>
                <option value="fact">Fact</option>
            </select>
            <select id="sort">
                <option value="created_at">Newest First</option>
                <option value="confidence_score">Confidence</option>
                <option value="reinforcement_count">Most Reinforced</option>
                <option value="category">Category</option>
                <option value="updated_at">Recently Updated</option>
            </select>
            <span class="text-muted" id="mem-count">Loading...</span>
        </div>'''

    table_html = '''
        <table>
            <thead>
                <tr>
                    <th>Content</th>
                    <th>Category</th>
                    <th class="hide-mobile">Confidence</th>
                    <th class="hide-mobile">Reinforced</th>
                    <th class="hide-mobile">Created</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="mem-tbody">
                <tr><td colspan="6" class="text-center text-muted">Loading memories...</td></tr>
            </tbody>
        </table>'''

    section_html = render_section("Semantic Memories", controls_html + table_html)

    page_content += nav_html
    page_content += section_html

    scripts = '''
    <script>
        const categoryEl = document.getElementById('category');
        const sortEl = document.getElementById('sort');
        const memTbody = document.getElementById('mem-tbody');
        const memCount = document.getElementById('mem-count');

        async function loadMemories() {
            const params = new URLSearchParams();
            const cat = categoryEl.value;
            const sort = sortEl.value;
            if (cat) params.set('category', cat);
            params.set('sort', sort);
            params.set('order', 'desc');
            try {
                const res = await fetch('/api/memories?' + params);
                const data = await res.json();
                memCount.textContent = data.length + ' memor' + (data.length === 1 ? 'y' : 'ies');
                memTbody.innerHTML = data.map(m => `
                    <tr>
                        <td class="content-cell">${esc(m.content)}</td>
                        <td><span class="badge badge-${m.category}">${m.category}</span></td>
                        <td class="hide-mobile score">${(m.confidence_score ?? 0).toFixed(2)}</td>
                        <td class="hide-mobile score">${m.reinforcement_count ?? 0}</td>
                        <td class="hide-mobile date">${fmtDate(m.created_at)}</td>
                        <td><button class="btn btn-danger" style="padding: 4px 8px; font-size: 0.75rem;" onclick="delMem(${m.memory_id})">Delete</button></td>
                    </tr>
                `).join('');
            } catch (err) {
                memTbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Failed to load memories.</td></tr>';
            }
        }

        async function delMem(id) {
            if (!confirm('Delete this memory?')) return;
            await fetch('/api/memories/' + id, { method: 'DELETE' });
            loadMemories();
        }

        categoryEl.addEventListener('change', loadMemories);
        sortEl.addEventListener('change', loadMemories);

        function esc(s) {
            const d = document.createElement('div');
            d.textContent = s ?? '';
            return d.innerHTML;
        }

        function fmtDate(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }

        loadMemories();
    </script>

    <style>
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-family { background: rgba(200, 146, 234, 0.2); color: #c792ea; }
        .badge-person { background: rgba(130, 170, 255, 0.2); color: #82aaff; }
        .badge-preference { background: rgba(195, 232, 141, 0.2); color: #c3e88d; }
        .badge-project { background: rgba(255, 203, 107, 0.2); color: #ffcb6b; }
        .badge-technical { background: rgba(137, 221, 255, 0.2); color: #89ddff; }
        .badge-event { background: rgba(128, 203, 196, 0.2); color: #80cbc4; }
        .badge-recurring_event { background: rgba(255, 83, 112, 0.2); color: #ff5370; }
        .badge-fact { background: rgba(240, 230, 140, 0.2); color: #f0e68c; }

        .content-cell { max-width: 500px; line-height: 1.4; }
        .score { font-variant-numeric: tabular-nums; color: var(--text-muted); }
        .date { white-space: nowrap; color: var(--text-faint); font-size: 0.8rem; }

        @media (max-width: 768px) {
            .hide-mobile { display: none; }
            .content-cell { max-width: 250px; }
        }
    </style>
    '''

    return render_html_page("Memories", page_content, extra_scripts=scripts)


MEMORIES_PAGE_HTML = get_memories_page_html()
