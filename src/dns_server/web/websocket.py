"""
DNS Server WebSocket Manager

This module provides real-time WebSocket communication for:
- Real-time DNS query/response streaming
- Client connection management
- Message broadcasting to connected clients
- DNS server events and notifications
"""

import asyncio
import json
import uuid
import weakref
from datetime import datetime
from typing import Dict, Optional, Set

from aiohttp import web_ws

from ..dns_logging import get_logger, get_request_tracker


class WebSocketManager:
    """Manages WebSocket connections and real-time updates."""

    def __init__(self, dns_server_app_ref):
        """Initialize WebSocket manager.

        Args:
            dns_server_app_ref: Weak reference to DNS server application
        """
        self.dns_server_app_ref = dns_server_app_ref
        self.logger = get_logger("websocket_manager")

        # Client connections
        self.clients: Dict[str, web_ws.WebSocketResponse] = {}

        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._is_running = False
        self._query_monitor_task: Optional[asyncio.Task] = None

    def get_dns_server_app(self):
        """Get DNS server application instance."""
        if self.dns_server_app_ref:
            return self.dns_server_app_ref()
        return None

    async def start(self) -> None:
        """Start WebSocket manager and background tasks."""
        if self._is_running:
            return

        self._is_running = True

        # Start query monitoring task
        self._query_monitor_task = asyncio.create_task(self._monitor_dns_queries())
        self._background_tasks.add(self._query_monitor_task)

        self.logger.info("WebSocket manager started")

    async def stop(self) -> None:
        """Stop WebSocket manager and cleanup connections."""
        self._is_running = False

        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._background_tasks.clear()

        # Close all client connections
        for client_id, ws in list(self.clients.items()):
            try:
                await ws.close()
            except Exception as ex:
                self.logger.warning(
                    "Error closing WebSocket connection",
                    client_id=client_id,
                    error=str(ex),
                )

        self.clients.clear()

        self.logger.info("WebSocket manager stopped")

    async def add_client(self, websocket: web_ws.WebSocketResponse) -> str:
        """Add a new WebSocket client.

        Args:
            websocket: WebSocket connection

        Returns:
            Client ID
        """
        client_id = str(uuid.uuid4())
        self.clients[client_id] = websocket

        # Send welcome message
        await self._send_to_client(
            client_id,
            {
                "type": "welcome",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "message": "Connected to DNS Server WebSocket",
            },
        )

        # Send current server status
        await self._send_server_status(client_id)

        self.logger.info(
            "WebSocket client added",
            client_id=client_id,
            total_clients=len(self.clients),
        )

        return client_id

    async def remove_client(self, client_id: str) -> None:
        """Remove a WebSocket client.

        Args:
            client_id: Client ID to remove
        """
        if client_id in self.clients:
            del self.clients[client_id]

            self.logger.info(
                "WebSocket client removed",
                client_id=client_id,
                total_clients=len(self.clients),
            )

    async def handle_message(self, client_id: str, message: dict) -> None:
        """Handle incoming WebSocket message from client.

        Args:
            client_id: Client ID
            message: Message data
        """
        try:
            message_type = message.get("type")

            if message_type == "ping":
                await self._send_to_client(
                    client_id,
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat() + "Z"},
                )

            elif message_type == "subscribe":
                # Handle subscription to specific events
                events = message.get("events", [])
                await self._handle_subscription(client_id, events)

            elif message_type == "get_status":
                # Send current server status
                await self._send_server_status(client_id)

            elif message_type == "get_recent_logs":
                # Send recent DNS logs
                await self._send_recent_logs(client_id, message.get("limit", 10))

            else:
                self.logger.warning(
                    "Unknown WebSocket message type",
                    client_id=client_id,
                    message_type=message_type,
                )

        except Exception as ex:
            self.logger.error(
                "Error handling WebSocket message", client_id=client_id, error=str(ex)
            )

    async def _handle_subscription(self, client_id: str, events: list) -> None:
        """Handle event subscription request.

        Args:
            client_id: Client ID
            events: List of events to subscribe to
        """
        # For now, all clients get all events
        # In the future, we could implement selective subscriptions
        await self._send_to_client(
            client_id,
            {
                "type": "subscription_confirmed",
                "events": events,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected clients.

        Args:
            message: Message to broadcast
        """
        if not self.clients:
            return

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Send to all clients
        disconnect_clients = []
        for client_id, ws in self.clients.items():
            try:
                if ws.closed:
                    disconnect_clients.append(client_id)
                else:
                    await ws.send_str(json.dumps(message))
            except Exception as ex:
                self.logger.warning(
                    "Error sending message to WebSocket client",
                    client_id=client_id,
                    error=str(ex),
                )
                disconnect_clients.append(client_id)

        # Remove disconnected clients
        for client_id in disconnect_clients:
            await self.remove_client(client_id)

    async def _send_to_client(self, client_id: str, message: dict) -> None:
        """Send message to specific client.

        Args:
            client_id: Client ID
            message: Message to send
        """
        if client_id not in self.clients:
            return

        ws = self.clients[client_id]

        try:
            if ws.closed:
                await self.remove_client(client_id)
            else:
                await ws.send_str(json.dumps(message))
        except Exception as ex:
            self.logger.warning(
                "Error sending message to WebSocket client",
                client_id=client_id,
                error=str(ex),
            )
            await self.remove_client(client_id)

    async def _send_server_status(self, client_id: str) -> None:
        """Send current server status to client.

        Args:
            client_id: Client ID
        """
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return

            # Get basic status
            status = {
                "type": "server_status",
                "status": "running"
                if dns_app.dns_server and dns_app.dns_server._is_running
                else "stopped",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            # Add DNS stats if available
            if dns_app.dns_server:
                dns_stats = dns_app.dns_server.get_stats()
                status["dns_stats"] = dns_stats

            # Add cache stats if available
            if dns_app.cache and hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()
                status["cache_stats"] = cache_stats

            await self._send_to_client(client_id, status)

        except Exception as ex:
            self.logger.error(
                "Error sending server status", client_id=client_id, error=str(ex)
            )

    async def _send_recent_logs(self, client_id: str, limit: int = 10) -> None:
        """Send recent DNS logs to client.

        Args:
            client_id: Client ID
            limit: Number of recent logs to send
        """
        try:
            request_tracker = get_request_tracker()
            if not request_tracker:
                return

            logs = []
            if hasattr(request_tracker, "get_recent_requests"):
                logs = await request_tracker.get_recent_requests(limit=limit)

            await self._send_to_client(
                client_id,
                {
                    "type": "recent_logs",
                    "logs": logs,
                    "count": len(logs),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )

        except Exception as ex:
            self.logger.error(
                "Error sending recent logs", client_id=client_id, error=str(ex)
            )

    async def _monitor_dns_queries(self) -> None:
        """Background task to monitor DNS queries and broadcast real-time updates."""
        self.logger.info("Starting DNS query monitoring")

        # Track last seen query to avoid duplicates
        last_query_time = datetime.utcnow().timestamp()

        while self._is_running:
            try:
                if not self.clients:
                    # No clients connected, sleep longer
                    await asyncio.sleep(1)
                    continue

                # Get recent queries since last check
                request_tracker = get_request_tracker()
                if request_tracker and hasattr(request_tracker, "get_recent_requests"):
                    # Get recent logs (last 10 seconds)
                    recent_logs = await request_tracker.get_recent_requests(limit=100)

                    # Filter for new queries
                    new_queries = []
                    current_time = datetime.utcnow().timestamp()

                    for log in recent_logs:
                        # Assuming log has timestamp
                        log_time = log.get("timestamp")
                        if log_time:
                            # Parse timestamp and compare
                            try:
                                if isinstance(log_time, str):
                                    log_timestamp = datetime.fromisoformat(
                                        log_time.replace("Z", "+00:00")
                                    ).timestamp()
                                else:
                                    log_timestamp = log_time

                                if log_timestamp > last_query_time:
                                    new_queries.append(log)
                            except Exception:
                                # If timestamp parsing fails, include the query
                                new_queries.append(log)

                    # Broadcast new queries
                    for query in new_queries:
                        await self.broadcast({"type": "dns_query", "query": query})

                    last_query_time = current_time

                # Send periodic server stats update
                await self._send_periodic_stats()

                # Sleep for a short interval
                await asyncio.sleep(0.5)  # Check every 500ms

            except asyncio.CancelledError:
                break
            except Exception as ex:
                self.logger.error("Error in DNS query monitoring", error=str(ex))
                await asyncio.sleep(1)  # Wait before retrying

        self.logger.info("DNS query monitoring stopped")

    async def _send_periodic_stats(self) -> None:
        """Send periodic statistics updates to all clients."""
        try:
            # Send stats update every 30 seconds
            if not hasattr(self, "_last_stats_time"):
                self._last_stats_time = 0

            current_time = datetime.utcnow().timestamp()
            if current_time - self._last_stats_time < 30:
                return

            self._last_stats_time = current_time

            dns_app = self.get_dns_server_app()
            if not dns_app:
                return

            # Compile stats
            stats = {
                "type": "stats_update",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            # DNS stats
            if dns_app.dns_server:
                dns_stats = dns_app.dns_server.get_stats()
                stats["dns_stats"] = dns_stats

            # Cache stats
            if dns_app.cache and hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()
                stats["cache_stats"] = cache_stats

            await self.broadcast(stats)

        except Exception as ex:
            self.logger.error("Error sending periodic stats", error=str(ex))

    def get_client_count(self) -> int:
        """Get number of connected clients.

        Returns:
            Number of connected clients
        """
        return len(self.clients)

    async def send_dns_query_update(self, query_data: dict) -> None:
        """Send real-time DNS query update to all clients.

        Args:
            query_data: DNS query data
        """
        await self.broadcast({"type": "dns_query", "query": query_data})

    async def send_cache_event(self, event_type: str, data: dict) -> None:
        """Send cache event to all clients.

        Args:
            event_type: Type of cache event (hit, miss, eviction, etc.)
            data: Event data
        """
        await self.broadcast(
            {"type": "cache_event", "event_type": event_type, "data": data}
        )

    async def send_server_event(
        self, event_type: str, message: str, data: dict = None
    ) -> None:
        """Send server event to all clients.

        Args:
            event_type: Type of server event
            message: Event message
            data: Optional event data
        """
        event = {"type": "server_event", "event_type": event_type, "message": message}

        if data:
            event["data"] = data

        await self.broadcast(event)
