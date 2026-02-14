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

import httpx
from langchain_core.tools import tool

from skippy.config import settings

logger = logging.getLogger("skippy")


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


# ============================================================================
# Notification Tools
# ============================================================================


@tool
def send_notification(message: str, title: str = "Skippy") -> str:
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
        return f"Notification sent successfully: '{title} - {message}'"
    except httpx.HTTPStatusError as e:
        logger.error("HA notification failed (HTTP %s): %s", e.response.status_code, e)
        return f"Failed to send notification (HTTP {e.response.status_code}): {e}"
    except Exception as e:
        logger.error("HA notification failed: %s", e)
        return f"Failed to send notification: {e}"


@tool
def send_sms(message: str) -> str:
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
        return f"SMS sent successfully to {settings.twilio_to_number}: '{message}'"
    except Exception as e:
        logger.error("SMS failed: %s", e)
        return f"Failed to send SMS: {e}"


# ============================================================================
# Generic State & Control Tools
# ============================================================================


@tool
def get_entity_state(entity_id: str) -> str:
    """Get the current state of any Home Assistant entity (sensor, light, switch, etc).

    Use this to check device status, sensor readings, or any entity state.
    Returns the state value and relevant attributes.

    Args:
        entity_id: The entity ID to query (e.g., 'light.living_room', 'sensor.temperature')
    """
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
def call_service(
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
        entity_id: Target entity (e.g., 'light.living_room')
        parameters: JSON string of additional parameters (e.g., '{"brightness": 180}')
    """
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
def turn_on_light(
    entity_id: str,
    brightness: int | None = None,
    color: str | None = None
) -> str:
    """Turn on a light with optional brightness and color.

    Args:
        entity_id: Light entity ID (e.g., 'light.living_room')
        brightness: Brightness 0-100 (optional, default is last value)
        color: Color name - 'red', 'green', 'blue', 'white', 'warm_white', 'cool_white' (optional)
    """
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
        return msg
    else:
        return f"Failed to turn on light: {result['error']}"


@tool
def turn_off_light(entity_id: str) -> str:
    """Turn off a light.

    Args:
        entity_id: Light entity ID (e.g., 'light.living_room')
    """
    result = _call_ha_service("light", "turn_off", entity_id)

    if result["success"]:
        return f"Turned off {entity_id}"
    else:
        return f"Failed to turn off light: {result['error']}"


# ============================================================================
# Switch Control Tools
# ============================================================================


@tool
def turn_on_switch(entity_id: str) -> str:
    """Turn on a switch.

    Args:
        entity_id: Switch entity ID (e.g., 'switch.living_room_fan')
    """
    result = _call_ha_service("switch", "turn_on", entity_id)
    return f"Turned on {entity_id}" if result["success"] else f"Failed: {result['error']}"


@tool
def turn_off_switch(entity_id: str) -> str:
    """Turn off a switch.

    Args:
        entity_id: Switch entity ID (e.g., 'switch.living_room_fan')
    """
    result = _call_ha_service("switch", "turn_off", entity_id)
    return f"Turned off {entity_id}" if result["success"] else f"Failed: {result['error']}"


# ============================================================================
# Climate Control Tools
# ============================================================================


@tool
def set_thermostat(
    entity_id: str,
    temperature: float,
    mode: str | None = None
) -> str:
    """Set thermostat temperature and optionally change HVAC mode.

    Args:
        entity_id: Climate entity ID (e.g., 'climate.living_room')
        temperature: Target temperature in Celsius
        mode: HVAC mode - 'heat', 'cool', 'heat_cool', 'auto', 'off' (optional)
    """
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

    return msg


# ============================================================================
# Lock Control Tools
# ============================================================================


@tool
def lock_door(entity_id: str) -> str:
    """Lock a door.

    Args:
        entity_id: Lock entity ID (e.g., 'lock.front_door')
    """
    result = _call_ha_service("lock", "lock", entity_id)
    return f"Locked {entity_id}" if result["success"] else f"Failed to lock: {result['error']}"


@tool
def unlock_door(entity_id: str) -> str:
    """Unlock a door.

    Args:
        entity_id: Lock entity ID (e.g., 'lock.front_door')
    """
    result = _call_ha_service("lock", "unlock", entity_id)
    return f"Unlocked {entity_id}" if result["success"] else f"Failed to unlock: {result['error']}"


# ============================================================================
# Cover Control Tools
# ============================================================================


@tool
def open_cover(entity_id: str) -> str:
    """Open a cover (blinds, garage door, etc).

    Args:
        entity_id: Cover entity ID (e.g., 'cover.garage_door', 'cover.living_room_blinds')
    """
    result = _call_ha_service("cover", "open_cover", entity_id)
    return f"Opening {entity_id}" if result["success"] else f"Failed to open: {result['error']}"


@tool
def close_cover(entity_id: str) -> str:
    """Close a cover (blinds, garage door, etc).

    Args:
        entity_id: Cover entity ID (e.g., 'cover.garage_door', 'cover.living_room_blinds')
    """
    result = _call_ha_service("cover", "close_cover", entity_id)
    return f"Closing {entity_id}" if result["success"] else f"Failed to close: {result['error']}"


@tool
def set_cover_position(entity_id: str, position: int) -> str:
    """Set cover position (blinds, shades, etc).

    Args:
        entity_id: Cover entity ID (e.g., 'cover.living_room_blinds')
        position: Position 0-100 (0 = closed, 100 = open)
    """
    if position < 0 or position > 100:
        return "Position must be 0-100"

    result = _call_ha_service("cover", "set_cover_position", entity_id, position=position)
    return f"Set {entity_id} to {position}%" if result["success"] else f"Failed: {result['error']}"


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
        tools.extend([
            # Generic
            get_entity_state,
            call_service,
            # Lights
            turn_on_light,
            turn_off_light,
            # Switches
            turn_on_switch,
            turn_off_switch,
            # Climate
            set_thermostat,
            # Locks
            lock_door,
            unlock_door,
            # Covers
            open_cover,
            close_cover,
            set_cover_position,
        ])

    return tools
