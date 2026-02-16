"""Home Assistant area and device synchronization.

Syncs areas and devices from HA to PostgreSQL for use in target resolution.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg

from skippy.config import settings
from skippy.ha.websocket_client import HAWebSocketClient

logger = logging.getLogger("skippy.ha.sync")


async def sync_areas_from_ha(
    ws_client: Optional[HAWebSocketClient], user_id: str = "nolan"
) -> dict[str, Any]:
    """Fetch areas from HA and sync to database.

    Args:
        ws_client: WebSocket client (if None, skips sync)
        user_id: User ID for multi-user support

    Returns:
        Summary dict with counts: {"areas_created": int, "areas_updated": int, "error": str}
    """
    if not ws_client or not ws_client.connected:
        logger.warning("WebSocket not connected, skipping area sync")
        return {"error": "WebSocket not connected", "areas_created": 0, "areas_updated": 0}

    try:
        # Fetch areas via WebSocket
        areas = await ws_client.fetch_registry("area_registry/list")
        if not areas:
            logger.warning("No areas returned from HA")
            return {"areas_created": 0, "areas_updated": 0}

        # Insert/update areas in database
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            created = 0
            updated = 0

            for area in areas:
                area_id = area.get("id")
                name = area.get("name", "Unknown")
                icon = area.get("icon")

                # Upsert into ha_areas
                result = await conn.execute(
                    """
                    INSERT INTO ha_areas (area_id, name, icon, user_id, last_synced)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (area_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        icon = EXCLUDED.icon,
                        last_synced = NOW()
                    """,
                    (area_id, name, icon, user_id),
                )

                if "INSERT" in result:
                    created += 1
                else:
                    updated += 1

            logger.info(f"Synced areas: {created} created, {updated} updated")
            return {"areas_created": created, "areas_updated": updated}

    except Exception as e:
        error_msg = f"Error syncing areas: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "areas_created": 0, "areas_updated": 0}


async def sync_devices_from_ha(
    ws_client: Optional[HAWebSocketClient], user_id: str = "nolan"
) -> dict[str, Any]:
    """Fetch devices from HA and sync to database.

    Args:
        ws_client: WebSocket client (if None, skips sync)
        user_id: User ID for multi-user support

    Returns:
        Summary dict with counts: {"devices_created": int, "devices_updated": int, "error": str}
    """
    if not ws_client or not ws_client.connected:
        logger.warning("WebSocket not connected, skipping device sync")
        return {"error": "WebSocket not connected", "devices_created": 0, "devices_updated": 0}

    try:
        # Fetch devices via WebSocket
        devices = await ws_client.fetch_registry("device_registry/list")
        if not devices:
            logger.warning("No devices returned from HA")
            return {"devices_created": 0, "devices_updated": 0}

        # Insert/update devices in database
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            created = 0
            updated = 0

            for device in devices:
                device_id = device.get("id")
                name = device.get("name", "Unknown")
                manufacturer = device.get("manufacturer")
                model = device.get("model")
                area_id = device.get("area_id")

                # Upsert into ha_devices
                result = await conn.execute(
                    """
                    INSERT INTO ha_devices
                        (device_id, name, manufacturer, model, area_id, user_id, last_synced)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (device_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        manufacturer = EXCLUDED.manufacturer,
                        model = EXCLUDED.model,
                        area_id = EXCLUDED.area_id,
                        last_synced = NOW()
                    """,
                    (device_id, name, manufacturer, model, area_id, user_id),
                )

                if "INSERT" in result:
                    created += 1
                else:
                    updated += 1

            logger.info(f"Synced devices: {created} created, {updated} updated")
            return {"devices_created": created, "devices_updated": updated}

    except Exception as e:
        error_msg = f"Error syncing devices: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "devices_created": 0, "devices_updated": 0}


async def sync_entity_area_mappings(
    ws_client: Optional[HAWebSocketClient], user_id: str = "nolan"
) -> dict[str, Any]:
    """Fetch entity registry and populate ha_entities.area_id via device linkage.

    This creates the relationship: Entity -> Device -> Area

    Args:
        ws_client: WebSocket client (if None, skips sync)
        user_id: User ID for multi-user support

    Returns:
        Summary dict with counts: {"entities_updated": int, "error": str}
    """
    if not ws_client or not ws_client.connected:
        logger.warning("WebSocket not connected, skipping entity area mapping")
        return {"error": "WebSocket not connected", "entities_updated": 0}

    try:
        # Fetch entity registry via WebSocket
        entity_registry = await ws_client.fetch_registry("entity_registry/list")
        if not entity_registry:
            logger.warning("No entities returned from HA")
            return {"entities_updated": 0}

        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            updated = 0

            # Build a map of entity_id -> area_id
            entity_area_map = {}
            for entity in entity_registry:
                entity_id = entity.get("entity_id")
                device_id = entity.get("device_id")

                if entity_id and device_id:
                    # Fetch area_id from device
                    cursor = await conn.execute(
                        "SELECT area_id FROM ha_devices WHERE device_id = %s",
                        (device_id,),
                    )
                    result = await cursor.fetchone()
                    if result:
                        area_id = result[0]
                        entity_area_map[entity_id] = area_id

            # Update ha_entities with area_id
            for entity_id, area_id in entity_area_map.items():
                result = await conn.execute(
                    "UPDATE ha_entities SET area_id = %s WHERE entity_id = %s",
                    (area_id, entity_id),
                )
                # Parse result string to check if rows were updated
                if "UPDATE" in result or "1 row" in result:
                    updated += 1

            logger.info(f"Updated {updated} entities with area mappings")
            return {"entities_updated": updated}

    except Exception as e:
        error_msg = f"Error syncing entity area mappings: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "entities_updated": 0}


async def sync_all_ha_data(
    ws_client: Optional[HAWebSocketClient], user_id: str = "nolan"
) -> dict[str, Any]:
    """Sync all HA data: areas, devices, and entity area mappings.

    Args:
        ws_client: WebSocket client
        user_id: User ID for multi-user support

    Returns:
        Combined summary dict
    """
    logger.info("Starting HA area/device sync...")

    areas_result = await sync_areas_from_ha(ws_client, user_id)
    devices_result = await sync_devices_from_ha(ws_client, user_id)
    mappings_result = await sync_entity_area_mappings(ws_client, user_id)

    summary = {
        "areas": areas_result,
        "devices": devices_result,
        "mappings": mappings_result,
    }

    logger.info(f"HA sync complete: {json.dumps(summary, indent=2)}")
    return summary
