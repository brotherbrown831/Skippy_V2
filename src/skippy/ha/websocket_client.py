"""Home Assistant WebSocket Client.

Provides async WebSocket communication with Home Assistant, supporting:
- Service calls with area_id/device_id/entity_id targeting
- State subscriptions and real-time updates
- Auto-reconnect with exponential backoff
- Graceful fallback to REST API on failure
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import httpx
import websockets
import websockets.client

from skippy.config import settings

logger = logging.getLogger("skippy.ha.websocket_client")


class HAWebSocketClient:
    """Home Assistant WebSocket client with auto-reconnect and fallback."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.msg_id_counter = 1
        self.subscriptions: dict[int, Callable] = {}
        self.pending_responses: dict[int, asyncio.Event] = {}
        self.response_data: dict[int, dict] = {}
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1.0  # Start with 1 second, exponential backoff
        self.last_error: Optional[str] = None
        self.last_connection_time: Optional[datetime] = None

    async def connect(self) -> bool:
        """Connect to Home Assistant WebSocket API."""
        try:
            # Convert HTTP URL to WebSocket URL
            ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://")
            if not ws_url.endswith("/api/websocket"):
                ws_url = ws_url.rstrip("/") + "/api/websocket"

            logger.info(f"Connecting to HA WebSocket: {ws_url}")
            self.websocket = await asyncio.wait_for(
                websockets.connect(ws_url, ping_interval=None),
                timeout=10.0,
            )

            # Receive auth_required message
            msg = json.loads(await self.websocket.recv())
            if msg.get("type") != "auth_required":
                raise ValueError(f"Expected auth_required, got {msg.get('type')}")

            # Send auth message
            await self.websocket.send(
                json.dumps(
                    {
                        "type": "auth",
                        "access_token": self.token,
                    }
                )
            )

            # Receive auth_ok or auth_invalid
            msg = json.loads(await self.websocket.recv())
            if msg.get("type") == "auth_ok":
                self.connected = True
                self.reconnect_attempts = 0
                self.reconnect_delay = 1.0
                self.last_error = None
                self.last_connection_time = datetime.now()
                logger.info("HA WebSocket connected and authenticated")

                # Start message listener task
                asyncio.create_task(self._listen_for_messages())
                return True
            else:
                error = msg.get("message", "Unknown auth error")
                raise ValueError(f"Authentication failed: {error}")

        except asyncio.TimeoutError:
            self.last_error = "Connection timeout"
            logger.error(f"HA WebSocket connection timeout")
            return False
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"HA WebSocket connection error: {e}")
            return False

    async def _listen_for_messages(self):
        """Listen for incoming messages from WebSocket."""
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_id = data.get("id")

                    # Route message to appropriate handler
                    if data.get("type") == "result":
                        # Response to a service call or query
                        if msg_id in self.response_data:
                            self.response_data[msg_id] = data
                            if msg_id in self.pending_responses:
                                self.pending_responses[msg_id].set()
                    elif data.get("type") == "event":
                        # State change event or subscription event
                        if msg_id in self.subscriptions:
                            callback = self.subscriptions[msg_id]
                            try:
                                asyncio.create_task(callback(data.get("event", {})))
                            except Exception as e:
                                logger.error(f"Error in subscription callback: {e}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {message}")
        except asyncio.CancelledError:
            logger.info("WebSocket message listener cancelled")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("HA WebSocket connection closed")
            self.connected = False
        except Exception as e:
            logger.error(f"Error listening to HA WebSocket: {e}")
            self.connected = False

    async def disconnect(self):
        """Disconnect from Home Assistant WebSocket."""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error disconnecting from WebSocket: {e}")
        self.websocket = None
        self.connected = False
        self.subscriptions.clear()
        self.pending_responses.clear()

    async def reconnect_loop(self):
        """Continuously attempt to reconnect with exponential backoff."""
        while True:
            if not self.connected:
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    await asyncio.sleep(self.reconnect_delay)
                    logger.info(
                        f"Reconnect attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts}"
                    )
                    success = await self.connect()
                    if success:
                        logger.info("HA WebSocket reconnected successfully")
                        break
                    else:
                        self.reconnect_attempts += 1
                        # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                        self.reconnect_delay = min(2 ** self.reconnect_attempts, 16.0)
                else:
                    logger.error(
                        "Max reconnect attempts reached. Will wait for manual intervention."
                    )
                    await asyncio.sleep(60)  # Wait 1 minute before retrying
            else:
                await asyncio.sleep(5)  # Check every 5 seconds when connected

    def _get_next_msg_id(self) -> int:
        """Get next message ID."""
        self.msg_id_counter += 1
        return self.msg_id_counter

    async def call_service(
        self,
        domain: str,
        service: str,
        target: Optional[dict[str, Any]] = None,
        service_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Call a Home Assistant service.

        Args:
            domain: Service domain (e.g., "light", "switch", "scene")
            service: Service name (e.g., "turn_on", "turn_off")
            target: Target dict with area_id, device_id, or entity_id (e.g., {"area_id": ["bedroom"]})
            service_data: Additional service data (e.g., {"brightness": 100})

        Returns:
            Response dict with "type": "result" and "success": bool
        """
        if not self.connected or not self.websocket:
            logger.warning("WebSocket not connected, falling back to REST API")
            return await self._call_service_rest(domain, service, target, service_data)

        try:
            msg_id = self._get_next_msg_id()
            payload = {
                "id": msg_id,
                "type": "call_service",
                "domain": domain,
                "service": service,
            }

            if target:
                payload["target"] = target
            if service_data:
                payload["service_data"] = service_data

            # Create event for response
            response_event = asyncio.Event()
            self.pending_responses[msg_id] = response_event

            # Send request
            await self.websocket.send(json.dumps(payload))

            # Wait for response with timeout
            try:
                await asyncio.wait_for(response_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error(f"Service call timeout: {domain}/{service}")
                return {"type": "result", "id": msg_id, "success": False, "error": "timeout"}

            # Get and return response
            response = self.response_data.pop(msg_id, {})
            self.pending_responses.pop(msg_id, None)

            if response.get("success"):
                logger.debug(f"Service call succeeded: {domain}/{service}")
                return response
            else:
                error = response.get("error", {})
                logger.error(f"Service call failed: {error}")
                return response

        except Exception as e:
            logger.error(f"Error calling service: {e}")
            # Fall back to REST API
            return await self._call_service_rest(domain, service, target, service_data)

    async def _call_service_rest(
        self,
        domain: str,
        service: str,
        target: Optional[dict[str, Any]] = None,
        service_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Fallback: Call service via REST API.

        Note: REST API doesn't support area_id/device_id targeting, so we'll
        need to expand targets to entity_id list first.
        """
        try:
            payload = {
                "type": "application/json",
            }

            # Build service data
            if service_data:
                payload.update(service_data)

            # If target has area_id or device_id, we need to expand to entity_ids
            if target and ("area_id" in target or "device_id" in target):
                # For now, just log a warning and attempt with the target as-is
                # In a full implementation, we'd query the DB to expand areas/devices to entities
                logger.warning(
                    f"REST fallback doesn't support area/device targeting, attempting anyway: {target}"
                )

            if target and "entity_id" in target:
                entity_ids = target.get("entity_id", [])
                if entity_ids:
                    payload["entity_id"] = entity_ids[0] if len(entity_ids) == 1 else entity_ids

            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{settings.ha_url}/api/services/{domain}/{service}"
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.ha_token}"},
                )

                if response.status_code in [200, 201]:
                    return {"type": "result", "success": True}
                else:
                    return {
                        "type": "result",
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                    }
        except Exception as e:
            logger.error(f"REST fallback error: {e}")
            return {"type": "result", "success": False, "error": str(e)}

    async def fetch_registry(self, registry_type: str) -> list[dict]:
        """Fetch a registry from Home Assistant.

        Args:
            registry_type: Type of registry to fetch
              - "area_registry/list"
              - "device_registry/list"
              - "entity_registry/list"

        Returns:
            List of registry items
        """
        # Try REST API first for registries (more reliable than WebSocket)
        return await self._fetch_registry_rest(registry_type)

    async def _fetch_registry_rest(self, registry_type: str) -> list[dict]:
        """Fetch registry via REST API (more reliable than WebSocket)."""
        try:
            url = f"{settings.ha_url}/api/config/{registry_type}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {settings.ha_token}"},
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"Fetched {len(data)} items from {registry_type}")
                    return data if isinstance(data, list) else []
                else:
                    logger.error(f"Failed to fetch registry (HTTP {response.status_code}): {registry_type}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching registry {registry_type} via REST: {e}")
            return []

    def get_connection_status(self) -> dict[str, Any]:
        """Get WebSocket connection status."""
        return {
            "connected": self.connected,
            "last_error": self.last_error,
            "reconnect_attempts": self.reconnect_attempts,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "last_connection_time": self.last_connection_time.isoformat()
            if self.last_connection_time
            else None,
        }


async def create_ha_websocket_client() -> HAWebSocketClient:
    """Create and connect a Home Assistant WebSocket client."""
    client = HAWebSocketClient(settings.ha_url, settings.ha_token)
    success = await client.connect()
    if success:
        # Start reconnect loop in background
        asyncio.create_task(client.reconnect_loop())
        return client
    else:
        logger.warning("Failed to connect to HA WebSocket on startup, will retry later")
        asyncio.create_task(client.reconnect_loop())
        return client
