"""Web API for Home Assistant entities management."""

import json
import logging

import psycopg
from fastapi import APIRouter, HTTPException

from skippy.config import settings

logger = logging.getLogger("skippy")

router = APIRouter()


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
