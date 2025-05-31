"""Configuration schema definitions for the DNS server.

This module defines the configuration structure using dataclasses with
built-in validation for all configuration parameters.
"""

import ipaddress
import os
from dataclasses import dataclass, field
from typing import List


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


def validate_port(port: int) -> bool:
    """Validate port number range."""
    return 1 <= port <= 65535


def validate_positive_int(value: int) -> bool:
    """Validate positive integer."""
    return value > 0


@dataclass
class ServerConfig:
    """Server configuration section."""

    bind_address: str = "127.0.0.1"
    dns_port: int = 5353
    web_port: int = 8080
    workers: int = 4

    def __post_init__(self) -> None:
        """Validate server configuration."""
        if not validate_ip_address(self.bind_address):
            raise ValueError(f"Invalid bind address: {self.bind_address}")

        if not validate_port(self.dns_port):
            raise ValueError(f"Invalid DNS port: {self.dns_port}")

        if not validate_port(self.web_port):
            raise ValueError(f"Invalid web port: {self.web_port}")

        if not validate_positive_int(self.workers):
            raise ValueError(f"Workers must be positive: {self.workers}")


@dataclass
class CacheConfig:
    """Cache configuration section."""

    max_size_mb: int = 100
    default_ttl: int = 300
    min_ttl: int = 1
    max_ttl: int = 86400
    negative_ttl: int = 300

    def __post_init__(self) -> None:
        """Validate cache configuration."""
        if not validate_positive_int(self.max_size_mb):
            raise ValueError(f"Cache size must be positive: {self.max_size_mb}")

        if not validate_positive_int(self.default_ttl):
            raise ValueError(f"Default TTL must be positive: {self.default_ttl}")

        if not validate_positive_int(self.min_ttl):
            raise ValueError(f"Min TTL must be positive: {self.min_ttl}")

        if not validate_positive_int(self.max_ttl):
            raise ValueError(f"Max TTL must be positive: {self.max_ttl}")

        if self.min_ttl > self.max_ttl:
            raise ValueError(
                f"Min TTL ({self.min_ttl}) cannot be greater than max TTL ({self.max_ttl})"
            )

        if not (1 <= self.max_ttl <= 86400):
            raise ValueError(
                f"Max TTL must be between 1 and 86400 seconds: {self.max_ttl}"
            )

        if not validate_positive_int(self.negative_ttl):
            raise ValueError(f"Negative TTL must be positive: {self.negative_ttl}")


@dataclass
class LoggingConfig:
    """Logging configuration section."""

    level: str = "INFO"
    format: str = "json"
    file: str = "logs/dns-server.log"
    max_size_mb: int = 50
    backup_count: int = 5

    def __post_init__(self) -> None:
        """Validate logging configuration."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {self.level}. Must be one of {valid_levels}"
            )

        valid_formats = {"json", "text"}
        if self.format.lower() not in valid_formats:
            raise ValueError(
                f"Invalid log format: {self.format}. Must be one of {valid_formats}"
            )

        if not validate_positive_int(self.max_size_mb):
            raise ValueError(f"Log max size must be positive: {self.max_size_mb}")

        if not validate_positive_int(self.backup_count):
            raise ValueError(f"Backup count must be positive: {self.backup_count}")

        # Ensure log directory exists
        log_dir = os.path.dirname(self.file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)


@dataclass
class SecurityConfig:
    """Security configuration section."""

    rate_limit_per_ip: int = 100
    allowed_networks: List[str] = field(default_factory=lambda: ["0.0.0.0/0"])
    blacklist_enabled: bool = True

    def __post_init__(self) -> None:
        """Validate security configuration."""
        if not validate_positive_int(self.rate_limit_per_ip):
            raise ValueError(f"Rate limit must be positive: {self.rate_limit_per_ip}")

        for network in self.allowed_networks:
            if not validate_network(network):
                raise ValueError(f"Invalid network format: {network}")


@dataclass
class WebConfig:
    """Web interface configuration section."""

    enabled: bool = True
    real_time_updates: bool = True
    history_limit: int = 1000

    def __post_init__(self) -> None:
        """Validate web configuration."""
        if not validate_positive_int(self.history_limit):
            raise ValueError(f"History limit must be positive: {self.history_limit}")


@dataclass
class DNSConfig:
    """Main DNS server configuration."""

    server: ServerConfig = field(default_factory=ServerConfig)
    upstream_servers: List[str] = field(
        default_factory=lambda: ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
    )
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def __post_init__(self) -> None:
        """Validate main configuration."""
        if not self.upstream_servers:
            raise ValueError("At least one upstream server must be configured")

        for server in self.upstream_servers:
            if not validate_ip_address(server):
                raise ValueError(f"Invalid upstream server IP: {server}")

        # Validate port conflicts
        if self.server.dns_port == self.server.web_port:
            raise ValueError("DNS and web ports cannot be the same")


def create_default_config() -> DNSConfig:
    """Create a default configuration instance."""
    return DNSConfig()


def validate_config(config: DNSConfig) -> bool:
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
