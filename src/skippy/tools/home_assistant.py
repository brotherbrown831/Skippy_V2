"""Home Assistant tools for Skippy.

Implements:
  - send_notification: Push notifications via HA Companion app
  - send_sms: SMS text messages via Twilio
  - get_entity_state: Read any entity state
  - call_service: Generic service caller
  - Light control: turn_on_light, turn_off_light
  - Switch control: turn_on_switch, turn_off_switch
  - Climate control: set_thermostat
  - Lock control: lock_door, unlock_door
  - Cover control: open_cover, close_cover, set_cover_position
"""

import json
import logging
from datetime import datetime, timedelta

import httpx
import psycopg
from langchain_core.tools import tool

from skippy.config import settings
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger("skippy")


# Entity cache with TTL
_entity_cache = {
    "entities": [],  # List of {entity_id, friendly_name, domain}
    "last_updated": None,  # datetime
    "ttl_seconds": 300  # 5 minutes
}


# ============================================================================
# Helper Functions (Internal, not exposed as tools)
# ============================================================================


def _get_ha_headers() -> dict:
    """Build HA API headers with auth token."""
    return {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json"
    }


def _call_ha_service(domain: str, service: str, entity_id: str, **kwargs) -> dict:
    """Generic HA service caller with error handling.

    Args:
        domain: Service domain (e.g., 'light', 'switch', 'climate')
        service: Service name (e.g., 'turn_on', 'turn_off')
        entity_id: Target entity ID (e.g., 'light.living_room')
        **kwargs: Additional service parameters

    Returns:
        Dict with 'success' (bool), 'data' (response), or 'error' (message)
    """
    try:
        url = f"{settings.ha_url}/api/services/{domain}/{service}"
        payload = {"entity_id": entity_id, **kwargs}

        response = httpx.post(url, json=payload, headers=_get_ha_headers(), timeout=10)
        response.raise_for_status()

        logger.info("HA service called: %s.%s on %s", domain, service, entity_id)
        return {"success": True, "data": response.json()}

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 401:
            logger.error("HA auth failed - check token validity")
            return {"success": False, "error": "Authentication failed"}
        elif status == 404:
            logger.error("HA entity not found: %s", entity_id)
            return {"success": False, "error": f"Entity {entity_id} not found"}
        elif status == 400:
            logger.error("HA bad request: %s", e.response.text)
            return {"success": False, "error": "Invalid request parameters"}
        else:
            logger.error("HA service failed (HTTP %s): %s", status, e)
            return {"success": False, "error": f"HTTP {status}"}

    except httpx.TimeoutException:
        logger.error("HA request timeout")
        return {"success": False, "error": "Request timeout"}

    except Exception as e:
        logger.error("HA service failed: %s", e)
        return {"success": False, "error": str(e)}


def _get_ha_state(entity_id: str) -> dict:
    """Get entity state with error handling.

    Args:
        entity_id: Entity ID to query (e.g., 'sensor.temperature')

    Returns:
        Dict with 'success' (bool), 'state', 'attributes', or 'error' (message)
    """
    try:
        url = f"{settings.ha_url}/api/states/{entity_id}"
        response = httpx.get(url, headers=_get_ha_headers(), timeout=5)
        response.raise_for_status()

        data = response.json()
        logger.info("HA state retrieved: %s = %s", entity_id, data.get("state"))
        return {
            "success": True,
            "entity_id": data["entity_id"],
            "state": data["state"],
            "attributes": data.get("attributes", {})
        }

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.error("HA entity not found: %s", entity_id)
            return {"success": False, "error": f"Entity {entity_id} not found"}
        elif e.response.status_code == 401:
            logger.error("HA auth failed")
            return {"success": False, "error": "Authentication failed"}
        else:
            logger.error("HA state retrieval failed: %s", e)
            return {"success": False, "error": str(e)}

    except Exception as e:
        logger.error("HA state retrieval failed: %s", e)
        return {"success": False, "error": str(e)}


def _fetch_ha_entities() -> list[dict]:
    """Fetch all entities from HA /api/states endpoint.

    Returns:
        List of dicts with: entity_id, friendly_name, domain
    """
    try:
        url = f"{settings.ha_url}/api/states"
        response = httpx.get(url, headers=_get_ha_headers(), timeout=10)
        response.raise_for_status()

        entities = []
        for entity in response.json():
            entity_id = entity.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            friendly_name = entity.get("attributes", {}).get("friendly_name", "")

            entities.append({
                "entity_id": entity_id,
                "friendly_name": friendly_name,
                "domain": domain
            })

        logger.info("Fetched %d entities from Home Assistant", len(entities))
        return entities

    except Exception as e:
        logger.error("Failed to fetch HA entities: %s", e)
        return []


def _get_cached_entities() -> list[dict]:
    """Return cached entities, refreshing if expired.

    Returns:
        List of entity dicts
    """
    now = datetime.now()
    last_updated = _entity_cache["last_updated"]
    ttl = timedelta(seconds=_entity_cache["ttl_seconds"])

    # Refresh if cache is empty or expired
    if not _entity_cache["entities"] or last_updated is None or (now - last_updated) > ttl:
        entities = _fetch_ha_entities()
        _entity_cache["entities"] = entities
        _entity_cache["last_updated"] = now
        logger.info("Entity cache refreshed (%d entities)", len(entities))

    return _entity_cache["entities"]


async def _resolve_entity_id(
    entity_id_or_name: str,
    domain: str | None = None,
    threshold: int = 85
) -> dict:
    """Resolve fuzzy entity name to exact entity_id with database alias support.

    Resolution priority:
    1. Exact database alias match
    2. Fuzzy database alias match (85+)
    3. Exact entity_id match
    4. Fuzzy match on entity_id/friendly_name from cache

    Args:
        entity_id_or_name: User input (e.g., 'office light' or 'light.officesw')
        domain: Optional domain filter (e.g., 'light', 'switch')
        threshold: Minimum fuzzy match score (default 85)

    Returns:
        {
            "entity_id": str,        # Resolved entity ID
            "confidence": float,     # Match score 0-100
            "matched_name": str,     # What was matched (entity_id or friendly_name)
            "suggestion": bool       # True if 70-84, requires user confirmation
        }

    Raises:
        ValueError: If no match found or score < 70
    """
    from rapidfuzz import process, fuzz

    # Normalize input
    query = entity_id_or_name.strip().lower()

    # Step 1: Check database for alias matches (exact, then fuzzy)
    try:
        async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
            async with conn.cursor() as cur:
                # Exact alias match
                domain_filter = "AND domain = %s" if domain else ""
                params = ["nolan", query]
                if domain:
                    params.append(domain)

                await cur.execute(
                    f"""
                    SELECT entity_id, friendly_name
                    FROM ha_entities
                    WHERE user_id = %s
                      AND enabled = TRUE
                      AND %s = ANY(SELECT LOWER(alias::text) FROM jsonb_array_elements_text(aliases) AS alias)
                      {domain_filter}
                    LIMIT 1
                    """,
                    params,
                )

                row = await cur.fetchone()
                if row:
                    return {
                        "entity_id": row[0],
                        "confidence": 100.0,
                        "matched_name": row[1] or row[0],
                        "suggestion": False,
                    }

                # Fuzzy match in database aliases
                domain_filter = "AND domain = %s" if domain else ""
                params = ["nolan"]
                if domain:
                    params.append(domain)

                await cur.execute(
                    f"""
                    SELECT entity_id, friendly_name, aliases
                    FROM ha_entities
                    WHERE user_id = %s
                      AND enabled = TRUE
                      {domain_filter}
                    ORDER BY entity_id
                    """,
                    params,
                )

                rows = await cur.fetchall()
                for row in rows:
                    aliases = row[2] or []
                    for alias in aliases:
                        score = fuzz.ratio(query, alias.lower())
                        if score >= 85:
                            return {
                                "entity_id": row[0],
                                "confidence": float(score),
                                "matched_name": alias,
                                "suggestion": False,
                            }

    except Exception:
        logger.exception("Failed to check database aliases, falling back to fuzzy matching")

    # Step 2: Fall back to cached entities fuzzy matching
    entities = _get_cached_entities()

    # Check for exact entity_id match first (fast path)
    for entity in entities:
        if entity["entity_id"].lower() == query:
            return {
                "entity_id": entity["entity_id"],
                "confidence": 100.0,
                "matched_name": entity["entity_id"],
                "suggestion": False
            }

    # Filter by domain if specified
    search_entities = entities
    if domain:
        search_entities = [e for e in entities if e["domain"] == domain]
        # Fall back to all domains if filtering returns nothing
        if not search_entities:
            logger.warning("No entities found in domain '%s', searching all domains", domain)
            search_entities = entities

    # Build search corpus: entity_ids + friendly_names + combined forms
    choices = []
    for entity in search_entities:
        # Add entity_id without domain prefix (e.g., "officesw" from "light.officesw")
        entity_name = entity["entity_id"].split(".", 1)[1] if "." in entity["entity_id"] else entity["entity_id"]
        choices.append((entity["entity_id"], entity_name.lower()))

        # Add friendly name if available
        if entity["friendly_name"]:
            choices.append((entity["entity_id"], entity["friendly_name"].lower()))

        # Add combined form: "light office" from domain + friendly_name
        if entity["friendly_name"]:
            combined = f"{entity['domain']} {entity['friendly_name']}".lower()
            choices.append((entity["entity_id"], combined))

    # Use rapidfuzz to find best match
    if not choices:
        raise ValueError("No entities available for matching")

    # Extract best match using WRatio scorer (handles partial matches well)
    result = process.extractOne(
        query,
        [choice[1] for choice in choices],
        scorer=fuzz.WRatio
    )

    if not result:
        raise ValueError(f"Could not find entity matching '{entity_id_or_name}'")

    matched_text, score, matched_idx = result
    matched_entity_id = choices[matched_idx][0]

    # Evaluate score and return result
    if score >= threshold:
        # High confidence - auto-use
        return {
            "entity_id": matched_entity_id,
            "confidence": float(score),
            "matched_name": matched_text,
            "suggestion": False
        }
    elif score >= 70:
        # Medium confidence - suggest to user
        return {
            "entity_id": matched_entity_id,
            "confidence": float(score),
            "matched_name": matched_text,
            "suggestion": True
        }
    else:
        # Low confidence - reject
        # Find top 3 similar entities for helpful error
        top_matches = process.extract(
            query,
            [choice[1] for choice in choices],
            scorer=fuzz.WRatio,
            limit=3
        )
        suggestions = [choices[m[2]][0] for m in top_matches]
        raise ValueError(
            f"Could not find entity matching '{entity_id_or_name}'. "
            f"Did you mean one of these? {', '.join(suggestions[:3])}"
        )


# ============================================================================
# New Consolidated Tools (Area/Device/Scene Aware)
# ============================================================================


@tool
async def control_device(
    target: str,
    action: str,
    parameters: dict | None = None
) -> str:
    """Control a Home Assistant device, area, scene, or entity.

    Intelligently resolves the target to a scene, area, device, or entity and performs
    the requested action. Supports natural language names like "bedroom", "desk lamp", etc.

    Args:
        target: What to control (area, device, entity, or scene name)
            - Area: "bedroom", "living room", "kitchen"
            - Device: "desk lamp", "smart plug", "thermostat"
            - Entity: "light.officesw", "switch.bedroom_fan"
            - Scene: "movie time", "bedtime"
        action: What to do (service name)
            - "turn_on", "turn_off" - Basic on/off
            - "toggle" - Switch state
            - "open", "close" - Covers/doors
            - "lock", "unlock" - Locks
            - "set_temperature" - Climate
            - "set_brightness" - Lights
        parameters: Additional service data as dict
            - {"brightness": 50} for lights
            - {"temperature": 72} for climate
            - {"position": 75} for covers

    Examples:
        - control_device(target="bedroom", action="turn_off")
        - control_device(target="desk lamp", action="turn_on", parameters={"brightness": 50})
        - control_device(target="movie time", action="turn_on")
    """
    from skippy.ha.resolver import resolve_target

    try:
        # Resolve target to scene/area/device/entity
        result = await resolve_target(target)

        if result.get("error"):
            return f"Error: {result['error']}"

        if result.get("suggestion"):
            return f"Did you mean '{result.get('matched_name')}'? Please confirm."

        target_type = result.get("target_type")
        target_dict = result.get("target_dict", {})

        # For scenes, always use scene.turn_on
        if target_type == "scene":
            # Get the actual entity_id from resolver
            entity_id = result.get("target_id")
            service_data = parameters or {}
            result_resp = _call_ha_service("scene", "turn_on", entity_id, **service_data)
            if result_resp["success"]:
                return f"Activated scene '{result.get('matched_name')}'"
            else:
                return f"Failed to activate scene: {result_resp.get('error')}"

        # For other targets, use WebSocket for area/device support
        from fastapi import FastAPI
        try:
            app = FastAPI()
            if hasattr(app.state, "ha_ws") and app.state.ha_ws:
                # Use WebSocket for area/device targeting
                domain_map = {
                    "turn_on": "light",  # Default to light, but will work for any domain
                    "turn_off": "light",
                    "toggle": "light",
                    "lock": "lock",
                    "unlock": "lock",
                    "open": "cover",
                    "close": "cover",
                    "set_brightness": "light",
                    "set_temperature": "climate",
                    "set_cover_position": "cover",
                }
                domain = domain_map.get(action, "homeassistant")

                ws_result = await app.state.ha_ws.call_service(
                    domain=domain,
                    service=action,
                    target=target_dict,
                    service_data=parameters or {},
                )

                if ws_result.get("success"):
                    return f"Action '{action}' completed on {result.get('matched_name')}"
                else:
                    return f"Action failed: {ws_result.get('error', 'Unknown error')}"
        except Exception:
            pass

        # Fallback to REST if WebSocket not available
        # For entities, use REST
        if target_type == "entity":
            entity_id = result.get("target_id")
            # Infer domain from entity_id
            if ":" in entity_id:
                domain = entity_id.split(":")[0]
            else:
                domain = entity_id.split(".")[0]

            rest_result = _call_ha_service(domain, action, entity_id, **(parameters or {}))
            if rest_result["success"]:
                return f"Action '{action}' completed on {result.get('matched_name')}"
            else:
                return f"Action failed: {rest_result.get('error')}"

        return "Unable to execute action - target type not supported"

    except Exception as e:
        logger.error(f"Error in control_device: {e}")
        return f"Error: {str(e)}"


@tool
async def activate_scene(scene_name: str) -> str:
    """Activate a Home Assistant scene.

    Scenes are pre-configured sets of entity states that can be activated with a single
    command. Examples: "movie time", "bedtime", "good morning".

    Args:
        scene_name: Name of the scene to activate (e.g., "movie time", "good morning")

    Examples:
        - activate_scene(scene_name="movie time")
        - activate_scene(scene_name="bedtime")
    """
    from skippy.ha.resolver import resolve_target

    try:
        # Resolve to a scene specifically
        result = await resolve_target(scene_name)

        if result.get("error"):
            return f"Error: {result['error']}"

        if result.get("target_type") != "scene":
            return f"'{scene_name}' doesn't match a known scene"

        if result.get("suggestion"):
            return f"Did you mean '{result.get('matched_name')}'? Please confirm."

        entity_id = result.get("target_id")

        # Call scene.turn_on
        response = _call_ha_service("scene", "turn_on", entity_id)
        if response["success"]:
            msg = f"Activated scene '{result.get('matched_name')}'"
            await log_activity(
                activity_type="scene_activated",
                entity_type="entity",
                entity_id=entity_id,
                description=msg,
                metadata={"scene_name": result.get('matched_name')},
                user_id="nolan",
            )
            return msg
        else:
            return f"Failed to activate scene: {response.get('error')}"

    except Exception as e:
        logger.error(f"Error activating scene: {e}")
        return f"Error: {str(e)}"


@tool
async def get_state(target: str) -> str:
    """Get the state of a Home Assistant entity, area, or device.

    Retrieves current state information for the specified target. For areas and devices,
    aggregates states of all entities in that area/device.

    Args:
        target: What to check
            - Area: "bedroom", "living room"
            - Device: "desk lamp", "thermostat"
            - Entity: "light.kitchen", "sensor.temperature"

    Examples:
        - get_state(target="bedroom") - Check if bedroom lights are on/off
        - get_state(target="temperature sensor")
        - get_state(target="light.living_room")
    """
    from skippy.ha.resolver import resolve_target

    try:
        # Resolve target
        result = await resolve_target(target)

        if result.get("error"):
            return f"Error: {result['error']}"

        if result.get("suggestion"):
            return f"Did you mean '{result.get('matched_name')}'? Please confirm."

        target_type = result.get("target_type")
        target_id = result.get("target_id")

        if target_type == "entity":
            # Get state of a single entity
            ha_result = _get_ha_state(target_id)
            if ha_result["success"]:
                state = ha_result["data"].get("state", "unknown")
                attributes = ha_result["data"].get("attributes", {})
                friendly_name = attributes.get("friendly_name", target_id)
                return f"{friendly_name} is {state}"
            else:
                return f"Unable to get state: {ha_result.get('error')}"

        elif target_type == "area":
            # Get aggregated state for area
            try:
                async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
                    cursor = await conn.execute(
                        """
                        SELECT entity_id, friendly_name FROM ha_entities
                        WHERE area_id = %s AND enabled = true
                        LIMIT 20
                        """,
                        (target_id,),
                    )
                    entities = await cursor.fetchall()

                    if not entities:
                        return f"No entities found in area '{result.get('matched_name')}'"

                    # Fetch states for all entities in area
                    states_summary = {}
                    for entity_id, friendly_name in entities:
                        state_result = _get_ha_state(entity_id)
                        if state_result["success"]:
                            state = state_result["data"].get("state", "unknown")
                            domain = entity_id.split(".")[0]
                            if domain not in states_summary:
                                states_summary[domain] = []
                            states_summary[domain].append(f"{friendly_name}:{state}")

                    # Format summary
                    summary = f"State of '{result.get('matched_name')}':\n"
                    for domain, entries in states_summary.items():
                        summary += f"  {domain.title()}: {', '.join(entries)}\n"
                    return summary.strip()
            except Exception as e:
                logger.error(f"Error getting area state: {e}")
                return f"Error getting area state: {e}"

        elif target_type == "device":
            # Get aggregated state for device
            try:
                async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
                    cursor = await conn.execute(
                        """
                        SELECT unnest(entity_ids) as entity_id FROM ha_devices
                        WHERE device_id = %s
                        """,
                        (target_id,),
                    )
                    entity_ids = await cursor.fetchall()

                    if not entity_ids:
                        return f"No entities found for device '{result.get('matched_name')}'"

                    # Fetch states
                    states = []
                    for (entity_id,) in entity_ids:
                        if entity_id:
                            state_result = _get_ha_state(entity_id)
                            if state_result["success"]:
                                state = state_result["data"].get("state", "unknown")
                                states.append(f"{entity_id}:{state}")

                    return f"State of '{result.get('matched_name')}': {', '.join(states)}"
            except Exception as e:
                logger.error(f"Error getting device state: {e}")
                return f"Error getting device state: {e}"

        return f"Unable to get state for {target_type}"

    except Exception as e:
        logger.error(f"Error in get_state: {e}")
        return f"Error: {str(e)}"


# ============================================================================
# Notification Tools
# ============================================================================


@tool
async def send_notification(message: str, title: str = "Skippy") -> str:
    """Send a push notification to the user's phone. Use this when you need to
    alert the user about something important, deliver a reminder, or when they
    explicitly ask you to send them a notification.

    Args:
        message: The notification body text.
        title: The notification title (defaults to "Skippy").
    """
    try:
        url = f"{settings.ha_url}/api/services/notify/{settings.ha_notify_service}"
        headers = _get_ha_headers()
        payload = {
            "message": message,
            "title": title,
        }

        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        logger.info("Notification sent: title='%s', message='%s'", title, message)
        msg = f"Notification sent successfully: '{title} - {message}'"
        await log_activity(
            activity_type="notification_sent",
            entity_type="system",
            entity_id="notification",
            description=f"Sent notification: {title}",
            metadata={"title": title, "message": message},
            user_id="nolan",
        )
        return msg
    except httpx.HTTPStatusError as e:
        logger.error("HA notification failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send notification (HTTP {e.response.status_code}): {e}"
    except Exception as e:
        logger.error("HA notification failed: %s", e)
        return f"Failed to send notification: {e}"


@tool
async def send_sms(message: str) -> str:
    """Send an SMS text message to the user's phone via Twilio. Use this for
    important or urgent messages, or when push notifications aren't reliable.
    Prefer send_notification for routine alerts and send_sms for higher-priority items.

    Args:
        message: The text message to send.
    """
    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        sms = client.messages.create(
            body=message,
            from_=settings.twilio_from_number,
            to=settings.twilio_to_number,
        )

        logger.info("SMS sent: sid=%s to=%s", sms.sid, settings.twilio_to_number)
        msg = f"SMS sent successfully to {settings.twilio_to_number}: '{message}'"
        await log_activity(
            activity_type="sms_sent",
            entity_type="system",
            entity_id="sms",
            description=f"Sent SMS message",
            metadata={"to": settings.twilio_to_number, "message": message},
            user_id="nolan",
        )
        return msg
    except Exception as e:
        logger.error("SMS failed: %s", e)
        return f"Failed to send SMS: {e}"


# ============================================================================
# Generic State & Control Tools
# ============================================================================


@tool
async def get_entity_state(entity_id: str) -> str:
    """Get the current state of any Home Assistant entity (sensor, light, switch, etc).

    Use this to check device status, sensor readings, or any entity state.
    Returns the state value and relevant attributes.

    Args:
        entity_id: The entity ID or name to query (e.g., 'light.living_room', 'temperature sensor', or 'sensor.temperature')
    """
    # Fuzzy entity resolution (no domain filter - searches all)
    try:
        resolved = await _resolve_entity_id(entity_id, domain=None, threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _get_ha_state(entity_id)

    if result["success"]:
        state = result["state"]
        attrs = result["attributes"]
        friendly_name = attrs.get("friendly_name", entity_id)
        unit = attrs.get("unit_of_measurement", "")

        response = f"{friendly_name}: {state}{unit}"

        # Add context for specific entity types
        if entity_id.startswith("light.") and state == "on":
            brightness = attrs.get("brightness")
            if brightness:
                response += f" (brightness: {int(brightness / 2.55)}%)"
        elif entity_id.startswith("climate."):
            temp = attrs.get("temperature")
            if temp:
                response += f" | target: {temp}°C"

        return response
    else:
        return f"Failed to get state: {result['error']}"


@tool
async def call_service(
    domain: str,
    service: str,
    entity_id: str,
    parameters: str = ""
) -> str:
    """Call any Home Assistant service on an entity. Advanced users only.

    This is a generic service caller for advanced control. Prefer specific tools
    like turn_on_light or set_thermostat for common operations.

    Args:
        domain: Service domain (e.g., 'light', 'switch', 'climate')
        service: Service name (e.g., 'turn_on', 'turn_off', 'toggle')
        entity_id: Target entity or name (e.g., 'light.living_room' or 'living room')
        parameters: JSON string of additional parameters (e.g., '{"brightness": 180}')
    """
    # Fuzzy entity resolution (no domain filter - user specifies domain via parameter)
    try:
        resolved = await _resolve_entity_id(entity_id, domain=None, threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    kwargs = {}
    if parameters:
        try:
            kwargs = json.loads(parameters)
        except json.JSONDecodeError:
            return f"Invalid parameters JSON: {parameters}"

    result = _call_ha_service(domain, service, entity_id, **kwargs)

    if result["success"]:
        return f"Successfully called {domain}.{service} on {entity_id}"
    else:
        return f"Failed to call service: {result['error']}"


# ============================================================================
# Light Control Tools
# ============================================================================


@tool
async def turn_on_light(
    entity_id: str,
    brightness: int | None = None,
    color: str | None = None
) -> str:
    """Turn on a light with optional brightness and color.

    Args:
        entity_id: Light entity ID or name (e.g., 'light.living_room' or 'living room light')
        brightness: Brightness 0-100 (optional, default is last value)
        color: Color name - 'red', 'green', 'blue', 'white', 'warm_white', 'cool_white' (optional)
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="light", threshold=85)

        # Handle suggestions (70-84 score)
        if resolved["suggestion"]:
            return (f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})? "
                    f"Please confirm or provide exact entity ID.")

        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    kwargs = {}

    if brightness is not None:
        if brightness < 0 or brightness > 100:
            return "Brightness must be 0-100"
        kwargs["brightness"] = int(brightness * 2.55)

    if color:
        color_map = {
            "red": {"rgb_color": [255, 0, 0]},
            "green": {"rgb_color": [0, 255, 0]},
            "blue": {"rgb_color": [0, 0, 255]},
            "white": {"rgb_color": [255, 255, 255]},
            "warm_white": {"color_temp_kelvin": 2700},
            "cool_white": {"color_temp_kelvin": 5000},
            "yellow": {"rgb_color": [255, 255, 0]},
            "purple": {"rgb_color": [128, 0, 128]},
            "orange": {"rgb_color": [255, 165, 0]}
        }

        if color.lower() in color_map:
            kwargs.update(color_map[color.lower()])
        else:
            return f"Unknown color '{color}'. Available: {', '.join(color_map.keys())}"

    result = _call_ha_service("light", "turn_on", entity_id, **kwargs)

    if result["success"]:
        msg = f"Turned on {entity_id}"
        if brightness:
            msg += f" at {brightness}%"
        if color:
            msg += f" ({color})"
        await log_activity(
            activity_type="light_turned_on",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={"brightness": brightness, "color": color},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to turn on light: {result['error']}"


@tool
async def turn_off_light(entity_id: str) -> str:
    """Turn off a light.

    Args:
        entity_id: Light entity ID or name (e.g., 'light.living_room' or 'living room light')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="light", threshold=85)

        if resolved["suggestion"]:
            return (f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})? "
                    f"Please confirm or provide exact entity ID.")

        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("light", "turn_off", entity_id)

    if result["success"]:
        msg = f"Turned off {entity_id}"
        await log_activity(
            activity_type="light_turned_off",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to turn off light: {result['error']}"


# ============================================================================
# Switch Control Tools
# ============================================================================


@tool
async def turn_on_switch(entity_id: str) -> str:
    """Turn on a switch.

    Args:
        entity_id: Switch entity ID or name (e.g., 'switch.fan' or 'fan')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="switch", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("switch", "turn_on", entity_id)
    if result["success"]:
        msg = f"Turned on {entity_id}"
        await log_activity(
            activity_type="switch_turned_on",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed: {result['error']}"


@tool
async def turn_off_switch(entity_id: str) -> str:
    """Turn off a switch.

    Args:
        entity_id: Switch entity ID or name (e.g., 'switch.fan' or 'fan')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="switch", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("switch", "turn_off", entity_id)
    if result["success"]:
        msg = f"Turned off {entity_id}"
        await log_activity(
            activity_type="switch_turned_off",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed: {result['error']}"


# ============================================================================
# Climate Control Tools
# ============================================================================


@tool
async def set_thermostat(
    entity_id: str,
    temperature: float,
    mode: str | None = None
) -> str:
    """Set thermostat temperature and optionally change HVAC mode.

    Args:
        entity_id: Climate entity ID or name (e.g., 'climate.living_room' or 'living room thermostat')
        temperature: Target temperature in Celsius
        mode: HVAC mode - 'heat', 'cool', 'heat_cool', 'auto', 'off' (optional)
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="climate", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    # Set temperature
    result = _call_ha_service("climate", "set_temperature", entity_id, temperature=temperature)

    if not result["success"]:
        return f"Failed to set temperature: {result['error']}"

    msg = f"Set {entity_id} to {temperature}°C"

    # Set mode if specified
    if mode:
        valid_modes = ["off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"]
        if mode.lower() not in valid_modes:
            return f"{msg}, but invalid mode '{mode}'. Valid: {', '.join(valid_modes)}"

        mode_result = _call_ha_service("climate", "set_hvac_mode", entity_id, hvac_mode=mode.lower())

        if mode_result["success"]:
            msg += f" in {mode} mode"
        else:
            msg += f", but failed to change mode: {mode_result['error']}"

    await log_activity(
        activity_type="thermostat_set",
        entity_type="entity",
        entity_id=entity_id,
        description=msg,
        metadata={"temperature": temperature, "mode": mode},
        user_id="nolan",
    )
    return msg


# ============================================================================
# Lock Control Tools
# ============================================================================


@tool
async def lock_door(entity_id: str) -> str:
    """Lock a door.

    Args:
        entity_id: Lock entity ID or name (e.g., 'lock.front_door' or 'front door')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="lock", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("lock", "lock", entity_id)
    if result["success"]:
        msg = f"Locked {entity_id}"
        await log_activity(
            activity_type="door_locked",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to lock: {result['error']}"


@tool
async def unlock_door(entity_id: str) -> str:
    """Unlock a door.

    Args:
        entity_id: Lock entity ID or name (e.g., 'lock.front_door' or 'front door')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="lock", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("lock", "unlock", entity_id)
    if result["success"]:
        msg = f"Unlocked {entity_id}"
        await log_activity(
            activity_type="door_unlocked",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to unlock: {result['error']}"


# ============================================================================
# Cover Control Tools
# ============================================================================


@tool
async def open_cover(entity_id: str) -> str:
    """Open a cover (blinds, garage door, etc).

    Args:
        entity_id: Cover entity ID or name (e.g., 'cover.garage_door' or 'garage door')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="cover", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("cover", "open_cover", entity_id)
    if result["success"]:
        msg = f"Opening {entity_id}"
        await log_activity(
            activity_type="cover_opened",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to open: {result['error']}"


@tool
async def close_cover(entity_id: str) -> str:
    """Close a cover (blinds, garage door, etc).

    Args:
        entity_id: Cover entity ID or name (e.g., 'cover.garage_door' or 'garage door')
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="cover", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    result = _call_ha_service("cover", "close_cover", entity_id)
    if result["success"]:
        msg = f"Closing {entity_id}"
        await log_activity(
            activity_type="cover_closed",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed to close: {result['error']}"


@tool
async def set_cover_position(entity_id: str, position: int) -> str:
    """Set cover position (blinds, shades, etc).

    Args:
        entity_id: Cover entity ID or name (e.g., 'cover.blinds' or 'blinds')
        position: Position 0-100 (0 = closed, 100 = open)
    """
    # Fuzzy entity resolution
    try:
        resolved = await _resolve_entity_id(entity_id, domain="cover", threshold=85)
        if resolved["suggestion"]:
            return f"Did you mean '{resolved['matched_name']}' ({resolved['entity_id']})?"
        entity_id = resolved["entity_id"]
    except ValueError as e:
        return str(e)

    if position < 0 or position > 100:
        return "Position must be 0-100"

    result = _call_ha_service("cover", "set_cover_position", entity_id, position=position)
    if result["success"]:
        msg = f"Set {entity_id} to {position}%"
        await log_activity(
            activity_type="cover_position_set",
            entity_type="entity",
            entity_id=entity_id,
            description=msg,
            metadata={"position": position},
            user_id="nolan",
        )
        return msg
    else:
        return f"Failed: {result['error']}"


# ============================================================================
# Tool Registration
# ============================================================================


def get_tools() -> list:
    """Return HA tools based on what's configured."""
    tools = []

    # Always include notifications if configured
    if settings.ha_token and settings.ha_notify_service:
        tools.append(send_notification)
    if settings.twilio_account_sid and settings.twilio_auth_token:
        tools.append(send_sms)

    # Add device control tools if HA is configured
    if settings.ha_token and settings.ha_url:
        # Add new consolidated tools first (higher priority for LLM)
        tools.extend([
            # New consolidated tools (area/device/scene aware)
            control_device,
            activate_scene,
            get_state,
            # Generic (legacy)
            get_entity_state,
            call_service,
            # Lights (legacy)
            turn_on_light,
            turn_off_light,
            # Switches (legacy)
            turn_on_switch,
            turn_off_switch,
            # Climate (legacy)
            set_thermostat,
            # Locks (legacy)
            lock_door,
            unlock_door,
            # Covers (legacy)
            open_cover,
            close_cover,
            set_cover_position,
        ])

    return tools
