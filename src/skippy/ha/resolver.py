"""Home Assistant target resolution.

Implements 4-tier resolution hierarchy:
1. Scenes (highest priority)
2. Areas
3. Devices
4. Entities (fallback to existing fuzzy matching)
"""

import logging
from typing import Any, Optional

from rapidfuzz import fuzz
import psycopg

from skippy.config import settings

logger = logging.getLogger("skippy.ha.resolver")


async def resolve_target(
    query: str,
    domain: Optional[str] = None,
    user_id: str = "nolan",
) -> dict[str, Any]:
    """Resolve natural language query to HA target.

    Args:
        query: User's natural language query (e.g., "bedroom", "movie time", "desk lamp")
        domain: Optional domain filter (e.g., "light", "switch") - only applicable to entities
        user_id: User ID for multi-user support

    Returns:
        {
            "target_type": "scene" | "area" | "device" | "entity",
            "target_id": str,  # scene.movie_time | area_id | device_id | entity_id
            "confidence": float,  # 0-100
            "matched_name": str,  # The actual name that matched
            "suggestion": bool,  # True if 70-84 confidence (user should confirm)
            "target_dict": dict,  # {"area_id": [...]} | {"device_id": [...]} | {"entity_id": [...]}
            "error": Optional[str],  # Error message if resolution failed
        }
    """
    query_lower = query.lower().strip()

    # Tier 1: Scenes (highest priority)
    scene_result = await _resolve_scene(query_lower, user_id)
    if scene_result and scene_result.get("confidence", 0) >= 70:
        return scene_result

    # Tier 2: Areas
    area_result = await _resolve_area(query_lower, user_id)
    if area_result and area_result.get("confidence", 0) >= 70:
        return area_result

    # Tier 3: Devices
    device_result = await _resolve_device(query_lower, user_id)
    if device_result and device_result.get("confidence", 0) >= 70:
        return device_result

    # Tier 4: Entities (fallback to existing fuzzy matching)
    entity_result = await _resolve_entity(query_lower, domain, user_id)
    if entity_result:
        return entity_result

    # No match found
    return {
        "target_type": None,
        "target_id": None,
        "confidence": 0.0,
        "matched_name": None,
        "suggestion": False,
        "target_dict": None,
        "error": f"No matching scene, area, device, or entity found for '{query}'",
    }


async def _resolve_scene(query: str, user_id: str) -> Optional[dict[str, Any]]:
    """Resolve to a scene entity."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            # Exact match on scene friendly_name
            cursor = await conn.execute(
                """
                SELECT entity_id, friendly_name, confidence FROM (
                    SELECT entity_id, friendly_name,
                           CASE WHEN LOWER(friendly_name) = %s THEN 100 ELSE 0 END as confidence
                    FROM ha_entities
                    WHERE domain = 'scene' AND enabled = true AND user_id = %s
                        AND LOWER(friendly_name) = %s
                ) t
                WHERE confidence > 0
                ORDER BY confidence DESC
                LIMIT 1
                """,
                (query, user_id, query),
            )
            result = await cursor.fetchone()

            if result:
                entity_id, friendly_name, confidence = result
                return {
                    "target_type": "scene",
                    "target_id": entity_id,
                    "confidence": float(confidence),
                    "matched_name": friendly_name,
                    "suggestion": False,
                    "target_dict": {"entity_id": [entity_id]},
                }

            # Fuzzy match on scene friendly_name and aliases
            cursor = await conn.execute(
                """
                SELECT entity_id, friendly_name, aliases FROM ha_entities
                WHERE domain = 'scene' AND enabled = true AND user_id = %s
                ORDER BY entity_id
                """,
                (user_id,),
            )
            scenes = await cursor.fetchall()

            best_match = None
            best_score = 0.0

            for entity_id, friendly_name, aliases in scenes:
                # Check friendly_name
                score = fuzz.ratio(query, friendly_name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_match = (entity_id, friendly_name, score * 100)

                # Check aliases
                if aliases:
                    for alias in aliases:
                        alias_score = fuzz.ratio(query, alias.lower()) / 100.0
                        if alias_score > best_score:
                            best_score = alias_score
                            best_match = (entity_id, alias, alias_score * 100)

            if best_match and best_score >= 0.70:
                entity_id, matched_name, confidence = best_match
                return {
                    "target_type": "scene",
                    "target_id": entity_id,
                    "confidence": confidence,
                    "matched_name": matched_name,
                    "suggestion": 70 <= confidence < 85,
                    "target_dict": {"entity_id": [entity_id]},
                }

    except Exception as e:
        logger.error(f"Error resolving scene: {e}")

    return None


async def _resolve_area(query: str, user_id: str) -> Optional[dict[str, Any]]:
    """Resolve to an area."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            # Exact match on area name
            cursor = await conn.execute(
                """
                SELECT area_id, name, 100 as confidence FROM ha_areas
                WHERE user_id = %s AND LOWER(name) = %s
                LIMIT 1
                """,
                (user_id, query),
            )
            result = await cursor.fetchone()

            if result:
                area_id, name, confidence = result
                return {
                    "target_type": "area",
                    "target_id": area_id,
                    "confidence": float(confidence),
                    "matched_name": name,
                    "suggestion": False,
                    "target_dict": {"area_id": [area_id]},
                }

            # Check aliases (exact match first, case-insensitive)
            cursor = await conn.execute(
                """
                SELECT area_id, name, aliases FROM ha_areas
                WHERE user_id = %s
                """,
                (user_id,),
            )
            areas = await cursor.fetchall()

            best_match = None
            best_score = 0.0

            for area_id, name, aliases in areas:
                # Fuzzy match on name
                score = fuzz.ratio(query, name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_match = (area_id, name, score * 100)

                # Fuzzy match on aliases
                if aliases:
                    for alias in aliases:
                        alias_score = fuzz.ratio(query, alias.lower()) / 100.0
                        if alias_score > best_score:
                            best_score = alias_score
                            best_match = (area_id, alias, alias_score * 100)

            if best_match and best_score >= 0.70:
                area_id, matched_name, confidence = best_match
                return {
                    "target_type": "area",
                    "target_id": area_id,
                    "confidence": confidence,
                    "matched_name": matched_name,
                    "suggestion": 70 <= confidence < 85,
                    "target_dict": {"area_id": [area_id]},
                }

    except Exception as e:
        logger.error(f"Error resolving area: {e}")

    return None


async def _resolve_device(query: str, user_id: str) -> Optional[dict[str, Any]]:
    """Resolve to a device."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            # Exact match on device name
            cursor = await conn.execute(
                """
                SELECT device_id, name, 100 as confidence FROM ha_devices
                WHERE user_id = %s AND LOWER(name) = %s AND enabled = true
                LIMIT 1
                """,
                (user_id, query),
            )
            result = await cursor.fetchone()

            if result:
                device_id, name, confidence = result
                return {
                    "target_type": "device",
                    "target_id": device_id,
                    "confidence": float(confidence),
                    "matched_name": name,
                    "suggestion": False,
                    "target_dict": {"device_id": [device_id]},
                }

            # Fuzzy match on device name and aliases
            cursor = await conn.execute(
                """
                SELECT device_id, name, aliases FROM ha_devices
                WHERE user_id = %s AND enabled = true
                """,
                (user_id,),
            )
            devices = await cursor.fetchall()

            best_match = None
            best_score = 0.0

            for device_id, name, aliases in devices:
                # Fuzzy match on name
                score = fuzz.ratio(query, name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_match = (device_id, name, score * 100)

                # Fuzzy match on aliases
                if aliases:
                    for alias in aliases:
                        alias_score = fuzz.ratio(query, alias.lower()) / 100.0
                        if alias_score > best_score:
                            best_score = alias_score
                            best_match = (device_id, alias, alias_score * 100)

            if best_match and best_score >= 0.70:
                device_id, matched_name, confidence = best_match
                return {
                    "target_type": "device",
                    "target_id": device_id,
                    "confidence": confidence,
                    "matched_name": matched_name,
                    "suggestion": 70 <= confidence < 85,
                    "target_dict": {"device_id": [device_id]},
                }

    except Exception as e:
        logger.error(f"Error resolving device: {e}")

    return None


async def _resolve_entity(
    query: str,
    domain: Optional[str] = None,
    user_id: str = "nolan",
) -> Optional[dict[str, Any]]:
    """Resolve to an entity (fallback, existing logic)."""
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            # Exact match on entity_id
            cursor = await conn.execute(
                """
                SELECT entity_id, friendly_name, domain, 100 as confidence
                FROM ha_entities
                WHERE entity_id = %s AND enabled = true AND user_id = %s
                """,
                (query, user_id),
            )
            result = await cursor.fetchone()

            if result:
                entity_id, friendly_name, domain, confidence = result
                return {
                    "target_type": "entity",
                    "target_id": entity_id,
                    "confidence": float(confidence),
                    "matched_name": friendly_name,
                    "suggestion": False,
                    "target_dict": {"entity_id": [entity_id]},
                }

            # Fuzzy match on aliases
            cursor = await conn.execute(
                """
                SELECT entity_id, friendly_name, aliases, domain
                FROM ha_entities
                WHERE enabled = true AND user_id = %s
                """,
                (user_id,),
            )
            entities = await cursor.fetchall()

            best_match = None
            best_score = 0.0

            for entity_id, friendly_name, aliases, entity_domain in entities:
                # Check domain filter if provided
                if domain and entity_domain != domain:
                    continue

                # Exact match on alias
                if aliases:
                    for alias in aliases:
                        if query == alias.lower():
                            return {
                                "target_type": "entity",
                                "target_id": entity_id,
                                "confidence": 100.0,
                                "matched_name": alias,
                                "suggestion": False,
                                "target_dict": {"entity_id": [entity_id]},
                            }

            # Fuzzy match on aliases and friendly_name
            for entity_id, friendly_name, aliases, entity_domain in entities:
                # Check domain filter if provided
                if domain and entity_domain != domain:
                    continue

                # Fuzzy match on friendly_name
                score = fuzz.token_set_ratio(query, friendly_name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_match = (entity_id, friendly_name, score * 100)

                # Fuzzy match on aliases
                if aliases:
                    for alias in aliases:
                        alias_score = fuzz.token_set_ratio(query, alias.lower()) / 100.0
                        if alias_score > best_score:
                            best_score = alias_score
                            best_match = (entity_id, alias, alias_score * 100)

            if best_match and best_score >= 0.70:
                entity_id, matched_name, confidence = best_match
                return {
                    "target_type": "entity",
                    "target_id": entity_id,
                    "confidence": confidence,
                    "matched_name": matched_name,
                    "suggestion": 70 <= confidence < 85,
                    "target_dict": {"entity_id": [entity_id]},
                }

    except Exception as e:
        logger.error(f"Error resolving entity: {e}")

    return None
