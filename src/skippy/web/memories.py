import logging
from datetime import datetime

import psycopg
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from skippy.config import settings

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
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
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
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
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


MEMORIES_PAGE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skippy's Memory Search</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
  }
  h1 { font-size: 1.6rem; margin-bottom: 4px; color: #7eb8ff; }
  .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 20px; }

  /* Tabs */
  .tabs {
    display: flex; gap: 0; margin-bottom: 24px;
    border-bottom: 2px solid #2a2d37;
  }
  .tab {
    padding: 10px 24px; cursor: pointer;
    color: #888; font-size: 0.9rem; font-weight: 600;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px; transition: all 0.2s;
  }
  .tab:hover { color: #aaa; }
  .tab.active { color: #7eb8ff; border-bottom-color: #7eb8ff; }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  .controls {
    display: flex; gap: 12px; flex-wrap: wrap;
    align-items: center; margin-bottom: 20px;
  }
  select {
    background: #1a1d27; color: #e0e0e0; border: 1px solid #333;
    padding: 6px 10px; border-radius: 6px; font-size: 0.85rem;
  }
  .count { color: #888; font-size: 0.85rem; margin-left: auto; }
  table {
    width: 100%; border-collapse: collapse;
    font-size: 0.85rem;
  }
  th {
    text-align: left; padding: 10px 12px;
    background: #1a1d27; color: #7eb8ff;
    border-bottom: 2px solid #2a2d37;
    position: sticky; top: 0;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #1e2130;
    vertical-align: top;
  }
  tr:hover td { background: #1a1d27; }
  .content-cell { max-width: 500px; line-height: 1.4; }
  .badge {
    display: inline-block; padding: 2px 8px;
    border-radius: 10px; font-size: 0.75rem;
    font-weight: 600; text-transform: uppercase;
  }
  .badge-family { background: #2d1f3d; color: #c792ea; }
  .badge-person { background: #1f2d3d; color: #82aaff; }
  .badge-preference { background: #2d3d1f; color: #c3e88d; }
  .badge-project { background: #3d2d1f; color: #ffcb6b; }
  .badge-technical { background: #1f3d3d; color: #89ddff; }
  .badge-event { background: #1f3d2d; color: #80cbc4; }
  .badge-recurring_event { background: #3d1f2d; color: #ff5370; }
  .badge-fact { background: #2d2d1f; color: #f0e68c; }
  .badge-rel { background: #1f2d3d; color: #82aaff; }
  .score {
    font-variant-numeric: tabular-nums;
    color: #aaa;
  }
  .date { white-space: nowrap; color: #777; font-size: 0.8rem; }
  .empty { color: #555; }
  .btn-del {
    background: transparent; border: 1px solid #444; color: #ff5370;
    padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 0.75rem;
  }
  .btn-del:hover { background: #2a1520; border-color: #ff5370; }
  @media (max-width: 768px) {
    .hide-mobile { display: none; }
    .content-cell { max-width: 250px; }
  }
</style>
</head>
<body>
<h1>Skippy's Memory Search</h1>
<p class="subtitle">All the things this magnificent AI remembers about you monkeys.</p>

<div class="tabs">
  <div class="tab active" data-tab="memories">Semantic Memories</div>
  <div class="tab" data-tab="people">People</div>
</div>

<!-- Memories Tab -->
<div id="tab-memories" class="tab-panel active">
  <div class="controls">
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
    <span class="count" id="mem-count"></span>
  </div>
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
    <tbody id="mem-tbody"></tbody>
  </table>
</div>

<!-- People Tab -->
<div id="tab-people" class="tab-panel">
  <p class="count" id="ppl-count" style="margin-bottom:16px"></p>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Relationship</th>
        <th>Birthday</th>
        <th class="hide-mobile">Address</th>
        <th class="hide-mobile">Phone</th>
        <th class="hide-mobile">Email</th>
        <th class="hide-mobile">Notes</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="ppl-tbody"></tbody>
  </table>
</div>

<script>
/* --- Tab switching --- */
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'people') loadPeople();
  });
});

/* --- Memories --- */
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
        <td><button class="btn-del" onclick="delMem(${m.memory_id})">Delete</button></td>
      </tr>
    `).join('');
  } catch (err) {
    memTbody.innerHTML = '<tr><td colspan="6">Failed to load memories.</td></tr>';
  }
}

async function delMem(id) {
  if (!confirm('Delete this memory?')) return;
  await fetch('/api/memories/' + id, { method: 'DELETE' });
  loadMemories();
}

categoryEl.addEventListener('change', loadMemories);
sortEl.addEventListener('change', loadMemories);

/* --- People --- */
const pplTbody = document.getElementById('ppl-tbody');
const pplCount = document.getElementById('ppl-count');

async function loadPeople() {
  try {
    const res = await fetch('/api/people');
    const data = await res.json();
    pplCount.textContent = data.length + ' ' + (data.length === 1 ? 'person' : 'people');
    pplTbody.innerHTML = data.map(p => `
      <tr>
        <td><strong>${esc(p.name)}</strong></td>
        <td>${p.relationship ? `<span class="badge badge-rel">${esc(p.relationship)}</span>` : e()}</td>
        <td>${esc(p.birthday) || e()}</td>
        <td class="hide-mobile">${esc(p.address) || e()}</td>
        <td class="hide-mobile">${esc(p.phone) || e()}</td>
        <td class="hide-mobile">${esc(p.email) || e()}</td>
        <td class="hide-mobile">${esc(p.notes) || e()}</td>
        <td><button class="btn-del" onclick="delPerson(${p.person_id})">Delete</button></td>
      </tr>
    `).join('');
  } catch (err) {
    pplTbody.innerHTML = '<tr><td colspan="8">Failed to load people.</td></tr>';
  }
}

async function delPerson(id) {
  if (!confirm('Delete this person?')) return;
  await fetch('/api/people/' + id, { method: 'DELETE' });
  loadPeople();
}

/* --- Helpers --- */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}
function e() { return '<span class="empty">\\u2014</span>'; }
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/* --- Init --- */
loadMemories();
</script>
</body>
</html>
"""
