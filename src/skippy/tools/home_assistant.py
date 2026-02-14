"""Home Assistant tools for Skippy.

This module will contain LangChain tools for controlling Home Assistant entities.
Tools to implement:
  - turn_on / turn_off (lights, switches, fans)
  - set_thermostat (climate entities)
  - get_sensor_state (temperature, humidity, motion)
  - lock / unlock (door locks)
  - trigger_scene (activate HA scenes)
  - get_entity_history (historical sensor data)

These tools will use the Home Assistant REST API via httpx:
  POST {HA_URL}/api/services/{domain}/{service}
  GET  {HA_URL}/api/states/{entity_id}

Auth: Bearer token via settings.ha_token
"""

from skippy.config import settings


def get_tools() -> list:
    """Return HA tools if configured. Not yet implemented."""
    if not settings.ha_token:
        return []
    # TODO: implement HA tools and return them here
    return []
