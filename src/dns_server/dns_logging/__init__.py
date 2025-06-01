"""
DNS Server Logging Module

This module provides structured JSON logging functionality for the DNS server
with request/response tracking, performance monitoring, and log management.
"""

from .dns_logger import (
    DNSRequestLogger,
    DNSRequestTracker,
    extract_dns_info,
    format_response_data,
    get_request_tracker,
    log_performance_event,
    log_security_event,
)
from .logger import (
    StructuredLogger,
    configure_logger_for_module,
    get_logger,
    log_exception,
    setup_logging,
)
from .manager import (
    LogManager,
    get_log_manager,
    setup_log_manager,
    start_log_management,
    stop_log_management,
)

__all__ = [
    # Core logging
    "StructuredLogger",
    "setup_logging",
    "get_logger",
    "log_exception",
    "configure_logger_for_module",
    # DNS-specific logging
    "DNSRequestLogger",
    "DNSRequestTracker",
    "get_request_tracker",
    "extract_dns_info",
    "format_response_data",
    "log_performance_event",
    "log_security_event",
    # Log management
    "LogManager",
    "get_log_manager",
    "setup_log_manager",
    "start_log_management",
    "stop_log_management",
]
