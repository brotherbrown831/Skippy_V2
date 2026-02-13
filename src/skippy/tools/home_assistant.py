# Home Assistant tools for Skippy
#
# This module will contain LangChain tools for controlling Home Assistant entities.
# The LangGraph agent graph is already wired to support tool calling — when tools
# are added to the `tools` list in agent/graph.py, the agent will automatically
# be able to use them.
#
# Example tools to implement:
#   - turn_on / turn_off (lights, switches, fans)
#   - set_thermostat (climate entities)
#   - get_sensor_state (temperature, humidity, motion)
#   - lock / unlock (door locks)
#   - trigger_scene (activate HA scenes)
#   - get_entity_history (historical sensor data)
#
# These tools will use the Home Assistant REST API via httpx:
#   POST {HA_URL}/api/services/{domain}/{service}
#   GET  {HA_URL}/api/states/{entity_id}
#
# Auth: Bearer token via settings.ha_token
