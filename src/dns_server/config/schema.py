"""
DNS Server Configuration Schema

Comprehensive configuration schema supporting security, performance, monitoring,
and operational settings for the DNS server.
"""

import ipaddress
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .validators import (
    validate_bind_address,
    validate_boolean,
    validate_file_path,
    validate_log_level,
    validate_positive_float,
    validate_positive_int,
    validate_port,
    validate_rate_limit,
    validate_server_address,
    validate_upstream_servers,
)


def validate_ip_address(ip: str) -> bool:
    """Validate IP address format."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_network(network: str) -> bool:
    """Validate network CIDR format."""
    try:
        ipaddress.ip_network(network, strict=False)
        return True
    except ValueError:
        return False


def validate_positive_int(value: int) -> bool:
    """Validate positive integer."""
    return value > 0


@dataclass
class ServerConfig:
    """Server configuration section."""

    bind_address: str = "127.0.0.1"
    dns_port: int = 9953
    web_port: int = 8080
    workers: int = 1
    max_concurrent_requests: int = 1000
    request_queue_size: int = 5000
    max_upstream_connections: int = 100
    connection_timeout: float = 30.0
    keepalive_timeout: float = 60.0
    max_clients: int = 1000

    def __post_init__(self) -> None:
        """Validate server configuration."""
        if not validate_bind_address(self.bind_address):
            raise ValueError(f"Invalid bind address: {self.bind_address}")

        if not validate_port(self.dns_port):
            raise ValueError(f"Invalid DNS port: {self.dns_port}")

        if not validate_port(self.web_port):
            raise ValueError(f"Invalid web port: {self.web_port}")

        if not validate_positive_int(self.workers):
            raise ValueError(f"Workers must be positive: {self.workers}")

        if not validate_positive_int(self.max_concurrent_requests):
            raise ValueError(
                f"Max concurrent requests must be positive: {self.max_concurrent_requests}"
            )

        if not validate_positive_int(self.request_queue_size):
            raise ValueError(
                f"Request queue size must be positive: {self.request_queue_size}"
            )

        if not validate_positive_int(self.max_upstream_connections):
            raise ValueError(
                f"Max upstream connections must be positive: {self.max_upstream_connections}"
            )

        if not validate_positive_float(self.connection_timeout):
            raise ValueError(
                f"Connection timeout must be positive: {self.connection_timeout}"
            )

        if not validate_positive_float(self.keepalive_timeout):
            raise ValueError(
                f"Keepalive timeout must be positive: {self.keepalive_timeout}"
            )

        if not validate_positive_int(self.max_clients):
            raise ValueError(f"Max clients must be positive: {self.max_clients}")


@dataclass
class SecurityConfig:
    """Security configuration section."""

    rate_limit_per_ip: int = 100
    block_malformed_requests: bool = True
    enable_dns_sec: bool = False
    enable_query_logging: bool = True
    allowed_query_types: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    whitelist_ips: Optional[List[str]] = None
    blacklist_ips: Optional[List[str]] = None
    max_query_length: int = 512
    enable_response_filtering: bool = False
    debug_client_ip: bool = False

    def __post_init__(self) -> None:
        """Validate security configuration."""
        if not validate_rate_limit(self.rate_limit_per_ip):
            raise ValueError(
                f"Rate limit per IP must be non-negative: {self.rate_limit_per_ip}"
            )

        if not validate_boolean(self.block_malformed_requests):
            raise ValueError(
                f"Block malformed requests must be boolean: {self.block_malformed_requests}"
            )

        if not validate_boolean(self.enable_dns_sec):
            raise ValueError(f"Enable DNSSEC must be boolean: {self.enable_dns_sec}")

        if not validate_boolean(self.enable_query_logging):
            raise ValueError(
                f"Enable query logging must be boolean: {self.enable_query_logging}"
            )

        if not validate_positive_int(self.max_query_length):
            raise ValueError(
                f"Max query length must be positive: {self.max_query_length}"
            )

        if not validate_boolean(self.enable_response_filtering):
            raise ValueError(
                f"Enable response filtering must be boolean: {self.enable_response_filtering}"
            )

        if not validate_boolean(self.debug_client_ip):
            raise ValueError(
                f"Debug client IP must be boolean: {self.debug_client_ip}"
            )


@dataclass
class LoggingConfig:
    """Logging configuration section."""

    level: str = "INFO"
    format: str = "structured"
    file: str = "logs/dns-server.log"
    max_size_mb: int = 100
    backup_count: int = 5
    enable_request_logging: bool = True
    log_query_details: bool = True
    log_performance_metrics: bool = True
    log_security_events: bool = True
    structured_format: str = "json"

    def __post_init__(self) -> None:
        """Validate logging configuration."""
        if not validate_log_level(self.level):
            raise ValueError(f"Invalid log level: {self.level}")

        if self.format not in ["simple", "detailed", "structured"]:
            raise ValueError(f"Invalid log format: {self.format}")

        if not validate_file_path(self.file):
            raise ValueError(f"Invalid log file path: {self.file}")

        if not validate_positive_int(self.max_size_mb):
            raise ValueError(f"Max size MB must be positive: {self.max_size_mb}")

        if not validate_positive_int(self.backup_count):
            raise ValueError(f"Backup count must be positive: {self.backup_count}")

        if not validate_boolean(self.enable_request_logging):
            raise ValueError(
                f"Enable request logging must be boolean: {self.enable_request_logging}"
            )

        if not validate_boolean(self.log_query_details):
            raise ValueError(
                f"Log query details must be boolean: {self.log_query_details}"
            )

        if not validate_boolean(self.log_performance_metrics):
            raise ValueError(
                f"Log performance metrics must be boolean: {self.log_performance_metrics}"
            )

        if not validate_boolean(self.log_security_events):
            raise ValueError(
                f"Log security events must be boolean: {self.log_security_events}"
            )

        if self.structured_format not in ["json", "key_value"]:
            raise ValueError(
                f"Invalid structured format: {self.structured_format}"
            )


@dataclass
class MonitoringConfig:
    """Monitoring configuration section."""

    enable_metrics: bool = True
    metrics_port: int = 9090
    enable_health_check: bool = True
    health_check_interval: int = 30
    performance_tracking: bool = True
    alert_on_high_error_rate: bool = True
    error_rate_threshold: float = 0.1
    alert_on_slow_queries: bool = True
    slow_query_threshold_ms: float = 1000.0

    def __post_init__(self) -> None:
        """Validate monitoring configuration."""
        if not validate_boolean(self.enable_metrics):
            raise ValueError(f"Enable metrics must be boolean: {self.enable_metrics}")

        if not validate_port(self.metrics_port):
            raise ValueError(f"Invalid metrics port: {self.metrics_port}")

        if not validate_boolean(self.enable_health_check):
            raise ValueError(
                f"Enable health check must be boolean: {self.enable_health_check}"
            )

        if not validate_positive_int(self.health_check_interval):
            raise ValueError(
                f"Health check interval must be positive: {self.health_check_interval}"
            )

        if not validate_boolean(self.performance_tracking):
            raise ValueError(
                f"Performance tracking must be boolean: {self.performance_tracking}"
            )

        if not validate_boolean(self.alert_on_high_error_rate):
            raise ValueError(
                f"Alert on high error rate must be boolean: {self.alert_on_high_error_rate}"
            )

        if not (0.0 <= self.error_rate_threshold <= 1.0):
            raise ValueError(
                f"Error rate threshold must be between 0.0 and 1.0: {self.error_rate_threshold}"
            )

        if not validate_boolean(self.alert_on_slow_queries):
            raise ValueError(
                f"Alert on slow queries must be boolean: {self.alert_on_slow_queries}"
            )

        if not validate_positive_float(self.slow_query_threshold_ms):
            raise ValueError(
                f"Slow query threshold must be positive: {self.slow_query_threshold_ms}"
            )


@dataclass
class WebConfig:
    """Web interface configuration section."""

    enabled: bool = True
    debug: bool = False
    cors_enabled: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    static_files_path: str = "web"
    api_rate_limit: int = 1000
    websocket_enabled: bool = True
    websocket_max_connections: int = 100

    def __post_init__(self) -> None:
        """Validate web configuration."""
        if not validate_boolean(self.enabled):
            raise ValueError(f"Web enabled must be boolean: {self.enabled}")

        if not validate_boolean(self.debug):
            raise ValueError(f"Web debug must be boolean: {self.debug}")

        if not validate_boolean(self.cors_enabled):
            raise ValueError(f"CORS enabled must be boolean: {self.cors_enabled}")

        if not isinstance(self.cors_origins, list):
            raise ValueError(f"CORS origins must be a list: {self.cors_origins}")

        if not validate_file_path(self.static_files_path):
            raise ValueError(f"Invalid static files path: {self.static_files_path}")

        if not validate_positive_int(self.api_rate_limit):
            raise ValueError(f"API rate limit must be positive: {self.api_rate_limit}")

        if not validate_boolean(self.websocket_enabled):
            raise ValueError(
                f"WebSocket enabled must be boolean: {self.websocket_enabled}"
            )

        if not validate_positive_int(self.websocket_max_connections):
            raise ValueError(
                f"WebSocket max connections must be positive: {self.websocket_max_connections}"
            )


@dataclass
class DNSServerConfig:
    """Main DNS server configuration."""

    # Core sections
    server: ServerConfig = field(default_factory=ServerConfig)
    upstream_servers: List[str] = field(
        default_factory=lambda: ["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"]
    )
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def __post_init__(self) -> None:
        """Validate the entire configuration."""
        if not validate_upstream_servers(self.upstream_servers):
            raise ValueError(f"Invalid upstream servers: {self.upstream_servers}")

        # Validate that ports don't conflict
        if self.server.dns_port == self.server.web_port:
            raise ValueError("DNS port and web port cannot be the same")

        if self.monitoring.enable_metrics and (
            self.monitoring.metrics_port == self.server.dns_port
            or self.monitoring.metrics_port == self.server.web_port
        ):
            raise ValueError("Metrics port conflicts with DNS or web port")


def create_default_config() -> DNSServerConfig:
    """Create a default configuration instance."""
    return DNSServerConfig()


def validate_config(config: DNSServerConfig) -> bool:
    """Validate a complete configuration instance.

    Args:
        config: Configuration instance to validate

    Returns:
        True if configuration is valid

    Raises:
        ValueError: If configuration is invalid
    """
    # Validation is performed in __post_init__ methods
    # This function can be extended for cross-section validation
    return True
