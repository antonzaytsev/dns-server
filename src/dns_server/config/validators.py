"""
Configuration Validators

This module provides validation functions for DNS server configuration parameters.
"""

import ipaddress
import os
import re
from pathlib import Path
from typing import List


def validate_bind_address(address: str) -> bool:
    """Validate bind address format."""
    if not address:
        return False
    
    # Allow 0.0.0.0 for all interfaces
    if address == "0.0.0.0":
        return True
    
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


def validate_boolean(value) -> bool:
    """Validate boolean value."""
    return isinstance(value, bool)


def validate_file_path(path: str) -> bool:
    """Validate file path format."""
    if not path:
        return False
    
    try:
        # Check if path is valid
        Path(path)
        return True
    except (TypeError, ValueError):
        return False


def validate_log_level(level: str) -> bool:
    """Validate log level."""
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    return level.upper() in valid_levels


def validate_positive_float(value: float) -> bool:
    """Validate positive float."""
    return isinstance(value, (int, float)) and value > 0


def validate_positive_int(value: int) -> bool:
    """Validate positive integer."""
    return isinstance(value, int) and value > 0


def validate_port(port: int) -> bool:
    """Validate port number."""
    return isinstance(port, int) and 1 <= port <= 65535


def validate_rate_limit(rate_limit: int) -> bool:
    """Validate rate limit (non-negative integer)."""
    return isinstance(rate_limit, int) and rate_limit >= 0


def validate_server_address(address: str) -> bool:
    """Validate server address format (IP:port or IP)."""
    if not address:
        return False
    
    # Split on last colon to handle IPv6 addresses
    if ":" in address:
        host, port_str = address.rsplit(":", 1)
        try:
            port = int(port_str)
            if not validate_port(port):
                return False
        except ValueError:
            return False
    else:
        host = address
    
    # Validate the host part
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        # Could be a hostname, check basic format
        return bool(re.match(r'^[a-zA-Z0-9.-]+$', host))


def validate_upstream_servers(servers: List[str]) -> bool:
    """Validate list of upstream servers."""
    if not isinstance(servers, list) or not servers:
        return False
    
    for server in servers:
        if not validate_server_address(server):
            return False
    
    return True 