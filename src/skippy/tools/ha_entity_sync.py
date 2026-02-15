"""Home Assistant entity sync and management tools."""

import json
import logging

import psycopg
from langchain_core.tools import tool

from skippy.config import settings
from skippy.tools.home_assistant import _fetch_ha_entities

logger = logging.getLogger("skippy")


async def sync_ha_entities_to_db(user_id: str = "nolan") -> dict:
    """Sync all Home Assistant entities to the database.

    This function:
    1. Fetches all entities from HA API
    2. Upserts into ha_entities table (preserves user customizations)
    3. Marks missing entities as disabled
    4. Returns sync statistics

    Returns:
        dict: {synced: int, disabled: int, errors: int}
    """
    try:
        # Step 1: Fetch all entities from HA
        entities = _fetch_ha_entities()
        logger.info(f"Fetched {len(entities)} entities from Home Assistant")

        synced = 0
        disabled = 0
        errors = 0

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Step 2: Get current entity_ids from database
                await cur.execute(
                    "SELECT entity_id FROM ha_entities WHERE user_id = %s AND enabled = TRUE",
                    (user_id,),
                )
                existing_ids = {row[0] for row in await cur.fetchall()}

                # Step 3: Upsert each entity
                ha_entity_ids = set()
                for entity in entities:
                    entity_id = entity.get("entity_id")
                    if not entity_id:
                        continue

                    ha_entity_ids.add(entity_id)

                    try:
                        # Upsert: update metadata, preserve user customizations
                        await cur.execute(
                            """
                            INSERT INTO ha_entities
                                (entity_id, domain, friendly_name, area, device_class,
                                 last_seen, enabled, user_id)
                            VALUES (%s, %s, %s, %s, %s, NOW(), TRUE, %s)
                            ON CONFLICT (entity_id) DO UPDATE SET
                                domain = EXCLUDED.domain,
                                friendly_name = EXCLUDED.friendly_name,
                                area = EXCLUDED.area,
                                device_class = EXCLUDED.device_class,
                                last_seen = NOW(),
                                enabled = TRUE,
                                updated_at = NOW()
                            """,
                            (
                                entity_id,
                                entity.get("domain"),
                                entity.get("friendly_name"),
                                entity.get("area"),
                                entity.get("device_class"),
                                user_id,
                            ),
                        )
                        synced += 1
                    except Exception:
                        logger.exception(f"Failed to sync entity {entity_id}")
                        errors += 1

                # Step 4: Mark missing entities as disabled
                missing_ids = existing_ids - ha_entity_ids
                if missing_ids:
                    await cur.execute(
                        """
                        UPDATE ha_entities
                        SET enabled = FALSE, updated_at = NOW()
                        WHERE user_id = %s AND entity_id = ANY(%s)
                        """,
                        (user_id, list(missing_ids)),
                    )
                    disabled = len(missing_ids)
                    logger.info(f"Marked {disabled} missing entities as disabled: {missing_ids}")

        logger.info(f"HA entity sync complete: {synced} synced, {disabled} disabled, {errors} errors")
        return {"synced": synced, "disabled": disabled, "errors": errors}

    except Exception:
        logger.exception("Failed to sync HA entities")
        return {"synced": 0, "disabled": 0, "errors": 1}


@tool
async def sync_ha_entities_now() -> str:
    """Manually trigger a sync of all Home Assistant entities to the database.

    Use this to refresh the entity list after adding/removing devices in Home Assistant.

    Returns:
        str: Sync result summary
    """
    stats = await sync_ha_entities_to_db()
    return (
        f"HA entity sync complete: {stats['synced']} entities synced, "
        f"{stats['disabled']} disabled, {stats['errors']} errors"
    )


@tool
async def search_ha_entities(
    query: str = "",
    domain: str | None = None,
    enabled_only: bool = True,
    user_id: str = "nolan",
) -> str:
    """Search Home Assistant entities in the database.

    Args:
        query: Search term (matches entity_id, friendly_name, aliases, area)
        domain: Filter by domain (e.g., "light", "switch")
        enabled_only: Only show enabled entities
        user_id: User ID

    Returns:
        str: JSON list of matching entities
    """
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Build query
                conditions = ["user_id = %s"]
                params = [user_id]

                if enabled_only:
                    conditions.append("enabled = TRUE")

                if domain:
                    conditions.append("domain = %s")
                    params.append(domain)

                if query:
                    conditions.append(
                        """(
                            entity_id ILIKE %s OR
                            friendly_name ILIKE %s OR
                            area ILIKE %s OR
                            aliases::text ILIKE %s
                        )"""
                    )
                    search_pattern = f"%{query}%"
                    params.extend([search_pattern] * 4)

                where_clause = " AND ".join(conditions)

                await cur.execute(
                    f"""
                    SELECT entity_id, domain, friendly_name, area, device_class,
                           aliases, enabled, rules, notes, last_seen
                    FROM ha_entities
                    WHERE {where_clause}
                    ORDER BY domain, friendly_name
                    LIMIT 100
                    """,
                    params,
                )

                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                results = []
                for row in rows:
                    entity = dict(zip(columns, row))
                    # Convert JSONB to dict
                    entity["aliases"] = entity.get("aliases") or []
                    entity["rules"] = entity.get("rules") or {}
                    # Format timestamp
                    if entity.get("last_seen"):
                        entity["last_seen"] = entity["last_seen"].isoformat()
                    results.append(entity)

                return json.dumps(results, indent=2)

    except Exception:
        logger.exception("Failed to search HA entities")
        return json.dumps({"error": "Failed to search entities"})


@tool
async def update_ha_entity(
    entity_id: str,
    aliases: list[str] | None = None,
    enabled: bool | None = None,
    rules: dict | None = None,
    notes: str | None = None,
    user_id: str = "nolan",
) -> str:
    """Update Home Assistant entity customizations.

    Args:
        entity_id: The HA entity ID (e.g., "light.officesw")
        aliases: User-defined aliases (e.g., ["office lights", "desk lamp"])
        enabled: Whether Skippy can control this entity
        rules: Behavior rules (see schema)
        notes: User notes
        user_id: User ID

    Returns:
        str: Success message or error
    """
    try:
        updates = []
        params = []

        if aliases is not None:
            updates.append("aliases = %s::jsonb")
            params.append(json.dumps(aliases))

        if enabled is not None:
            updates.append("enabled = %s")
            params.append(enabled)

        if rules is not None:
            updates.append("rules = %s::jsonb")
            params.append(json.dumps(rules))

        if notes is not None:
            updates.append("notes = %s")
            params.append(notes)

        if not updates:
            return "No updates provided"

        updates.append("updated_at = NOW()")
        params.extend([entity_id, user_id])

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    UPDATE ha_entities
                    SET {', '.join(updates)}
                    WHERE entity_id = %s AND user_id = %s
                    RETURNING entity_id, friendly_name
                    """,
                    params,
                )

                row = await cur.fetchone()
                if not row:
                    return f"Entity not found: {entity_id}"

                return f"Updated entity {row[0]} ({row[1]})"

    except Exception:
        logger.exception(f"Failed to update entity {entity_id}")
        return f"Error updating entity: {entity_id}"


def get_tools() -> list:
    """Return HA entity management tools."""
    return [sync_ha_entities_now, search_ha_entities, update_ha_entity]
