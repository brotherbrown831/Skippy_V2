"""Web API and UI for Home Assistant entities management."""

import json
import logging

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


@router.get("/entities", response_class=HTMLResponse)
async def entities_page():
    """Serve the HA entities viewer page."""
    return ENTITIES_PAGE_HTML


@router.get("/api/ha_entities")
async def get_ha_entities(
    domain: str | None = None,
    enabled: bool | None = None,
    search: str | None = None,
):
    """Get all HA entities with optional filtering."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                conditions = ["user_id = 'nolan'"]
                params = []

                if domain:
                    conditions.append("domain = %s")
                    params.append(domain)

                if enabled is not None:
                    conditions.append("enabled = %s")
                    params.append(enabled)

                if search:
                    conditions.append(
                        "(entity_id ILIKE %s OR friendly_name ILIKE %s OR area ILIKE %s)"
                    )
                    pattern = f"%{search}%"
                    params.extend([pattern, pattern, pattern])

                where_clause = " AND ".join(conditions)

                await cur.execute(
                    f"""
                    SELECT entity_id, domain, friendly_name, area, device_class, device_id,
                           aliases, enabled, rules, notes, last_seen, created_at, updated_at
                    FROM ha_entities
                    WHERE {where_clause}
                    ORDER BY domain, friendly_name
                    """,
                    params,
                )

                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                results = []
                for row in rows:
                    entity = dict(zip(columns, row))
                    entity["aliases"] = entity.get("aliases") or []
                    entity["rules"] = entity.get("rules") or {}
                    if entity.get("last_seen"):
                        entity["last_seen"] = entity["last_seen"].isoformat()
                    if entity.get("created_at"):
                        entity["created_at"] = entity["created_at"].isoformat()
                    if entity.get("updated_at"):
                        entity["updated_at"] = entity["updated_at"].isoformat()
                    results.append(entity)

                return results

    except Exception:
        logger.exception("Failed to fetch HA entities")
        raise HTTPException(status_code=500, detail="Failed to fetch entities")


@router.post("/api/ha_entities/sync")
async def sync_entities_api():
    """Trigger manual entity sync."""
    from skippy.tools.ha_entity_sync import sync_ha_entities_to_db

    stats = await sync_ha_entities_to_db()
    return stats


@router.put("/api/ha_entities/{entity_id}")
async def update_ha_entity_api(entity_id: str, data: dict):
    """Update HA entity customizations."""
    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                updates = []
                params = []

                if "aliases" in data:
                    updates.append("aliases = %s::jsonb")
                    params.append(json.dumps(data["aliases"]))

                if "enabled" in data:
                    updates.append("enabled = %s")
                    params.append(data["enabled"])

                if "rules" in data:
                    updates.append("rules = %s::jsonb")
                    params.append(json.dumps(data["rules"]))

                if "notes" in data:
                    updates.append("notes = %s")
                    params.append(data["notes"])

                if not updates:
                    raise HTTPException(status_code=400, detail="No updates provided")

                updates.append("updated_at = NOW()")
                params.extend([entity_id, "nolan"])

                await cur.execute(
                    f"""
                    UPDATE ha_entities
                    SET {', '.join(updates)}
                    WHERE entity_id = %s AND user_id = %s
                    RETURNING entity_id, friendly_name, aliases, enabled, rules, notes
                    """,
                    params,
                )

                row = await cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Entity not found")

                columns = [desc.name for desc in cur.description]
                result = dict(zip(columns, row))
                result["aliases"] = result.get("aliases") or []
                result["rules"] = result.get("rules") or {}

                return result

    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to update entity {entity_id}")
        raise HTTPException(status_code=500, detail="Failed to update entity")


ENTITIES_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Home Assistant Entities</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #0f1117;
            color: #e0e0e0;
        }
        h1 { color: #7eb8ff; margin-top: 0; margin-bottom: 8px; }
        .subtitle { color: #888; font-size: 0.9em; margin-bottom: 20px; }
        .controls {
            display: flex; gap: 12px; flex-wrap: wrap;
            align-items: center; margin-bottom: 20px;
        }
        select, input {
            background: #1a1d27;
            color: #e0e0e0;
            border: 1px solid #333;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 0.85em;
        }
        .count { color: #888; font-size: 0.85em; margin-left: auto; }
        table {
            width: 100%;
            background: #1a1d27;
            border-collapse: collapse;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        thead {
            background: #0f1117;
            font-weight: bold;
            border-bottom: 2px solid #2a2d37;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
        }
        tbody tr:hover {
            background: #222530;
        }
        tbody tr:nth-child(even) {
            background: #161a22;
        }
        .domain-badge {
            display: inline-block;
            background: #1f3d3d;
            color: #89ddff;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 600;
            text-transform: uppercase;
        }
        .enabled { color: #90ee90; }
        .disabled { color: #ff6b6b; }
        .empty { color: #555; }
        @media (max-width: 768px) {
            .hide-mobile { display: none; }
        }
    </style>
</head>
<body>
    <h1>🏠 Home Assistant Entities</h1>
    <p class="subtitle">All your Smart Home devices and integrations</p>

    <div class="controls">
        <select id="domain-filter">
            <option value="">All Domains</option>
        </select>
        <select id="enabled-filter">
            <option value="">All Status</option>
            <option value="true">Enabled Only</option>
            <option value="false">Disabled Only</option>
        </select>
        <input type="text" id="search-input" placeholder="Search entities..." style="flex: 1; max-width: 300px;">
        <div class="count"><span id="entity-count">-</span> entities</div>
    </div>

    <table id="entities-table">
        <thead>
            <tr>
                <th>Entity ID</th>
                <th>Friendly Name</th>
                <th>Domain</th>
                <th class="hide-mobile">Area</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody id="entities-body">
            <tr><td colspan="5" class="empty">Loading...</td></tr>
        </tbody>
    </table>

    <script>
        let allEntities = [];
        let domains = new Set();

        async function loadEntities(filters = {}) {
            try {
                const params = new URLSearchParams();
                if (filters.domain) params.append('domain', filters.domain);
                if (filters.enabled !== undefined) params.append('enabled', filters.enabled);
                if (filters.search) params.append('search', filters.search);

                const response = await fetch('/api/ha_entities?' + params);
                allEntities = await response.json();

                // Extract unique domains
                allEntities.forEach(e => domains.add(e.domain));
                updateDomainFilter();
                renderTable();
            } catch (error) {
                console.error('Failed to load entities:', error);
                document.getElementById('entities-body').innerHTML = '<tr><td colspan="5" class="empty">Error loading entities</td></tr>';
            }
        }

        function updateDomainFilter() {
            const select = document.getElementById('domain-filter');
            const currentValue = select.value;
            select.innerHTML = '<option value="">All Domains</option>';
            Array.from(domains).sort().forEach(domain => {
                const option = document.createElement('option');
                option.value = domain;
                option.textContent = domain;
                select.appendChild(option);
            });
            select.value = currentValue;
        }

        function renderTable() {
            const tbody = document.getElementById('entities-body');
            if (allEntities.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty">No entities found</td></tr>';
                document.getElementById('entity-count').textContent = '0';
                return;
            }

            tbody.innerHTML = allEntities.map(e => `
                <tr>
                    <td><code style="color: #89ddff;">${e.entity_id}</code></td>
                    <td>${e.friendly_name || e.entity_id}</td>
                    <td><span class="domain-badge">${e.domain}</span></td>
                    <td class="hide-mobile">${e.area || '-'}</td>
                    <td><span class="${e.enabled ? 'enabled' : 'disabled'}">${e.enabled ? '✓ Enabled' : '✗ Disabled'}</span></td>
                </tr>
            `).join('');

            document.getElementById('entity-count').textContent = allEntities.length;
        }

        // Event listeners for filters
        document.getElementById('domain-filter').addEventListener('change', () => applyFilters());
        document.getElementById('enabled-filter').addEventListener('change', () => applyFilters());
        document.getElementById('search-input').addEventListener('input', () => applyFilters());

        function applyFilters() {
            const filters = {
                domain: document.getElementById('domain-filter').value || undefined,
                enabled: document.getElementById('enabled-filter').value ?
                    document.getElementById('enabled-filter').value === 'true' : undefined,
                search: document.getElementById('search-input').value || undefined
            };
            loadEntities(filters);
        }

        // Initial load
        loadEntities();
        // Auto-refresh every 60 seconds
        setInterval(() => applyFilters(), 60000);
    </script>
</body>
</html>
"""
