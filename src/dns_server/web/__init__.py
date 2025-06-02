"""
DNS Server Web Interface Module

This module provides the web interface for the DNS server including:
- REST API endpoints for monitoring and control
- Static file serving for the dashboard
"""

from .server import WebServer

__all__ = ["WebServer"]
