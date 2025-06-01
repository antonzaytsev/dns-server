"""
DNS Server Web Interface Module

This module provides the web interface for the DNS server including:
- REST API endpoints for monitoring and control
- WebSocket real-time updates
- Static file serving for the dashboard
"""

from .server import WebServer
from .websocket import WebSocketManager

__all__ = ["WebServer", "WebSocketManager"]
