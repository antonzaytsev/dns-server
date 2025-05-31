"""Tests for the configuration schema module."""

import pytest

from src.dns_server.config.schema import (
    CacheConfig,
    DNSConfig,
    LoggingConfig,
    SecurityConfig,
    ServerConfig,
    create_default_config,
    validate_config,
    validate_ip_address,
    validate_network,
    validate_port,
    validate_positive_int,
)


class TestValidationFunctions:
    """Test validation utility functions."""

    def test_validate_ip_address(self):
        """Test IP address validation."""
        assert validate_ip_address("127.0.0.1") is True
        assert validate_ip_address("::1") is True
        assert validate_ip_address("8.8.8.8") is True
        assert validate_ip_address("invalid") is False
        assert validate_ip_address("256.1.1.1") is False

    def test_validate_network(self):
        """Test network CIDR validation."""
        assert validate_network("192.168.1.0/24") is True
        assert validate_network("0.0.0.0/0") is True
        assert validate_network("10.0.0.0/8") is True
        assert validate_network("invalid") is False
        assert validate_network("192.168.1.0/33") is False

    def test_validate_port(self):
        """Test port number validation."""
        assert validate_port(80) is True
        assert validate_port(65535) is True
        assert validate_port(1) is True
        assert validate_port(0) is False
        assert validate_port(65536) is False
        assert validate_port(-1) is False

    def test_validate_positive_int(self):
        """Test positive integer validation."""
        assert validate_positive_int(1) is True
        assert validate_positive_int(100) is True
        assert validate_positive_int(0) is False
        assert validate_positive_int(-1) is False


class TestServerConfig:
    """Test ServerConfig validation."""

    def test_valid_server_config(self):
        """Test valid server configuration."""
        config = ServerConfig(
            bind_address="127.0.0.1", dns_port=5353, web_port=8080, workers=4
        )
        assert config.bind_address == "127.0.0.1"
        assert config.dns_port == 5353

    def test_invalid_bind_address(self):
        """Test invalid bind address."""
        with pytest.raises(ValueError, match="Invalid bind address"):
            ServerConfig(bind_address="invalid")

    def test_invalid_dns_port(self):
        """Test invalid DNS port."""
        with pytest.raises(ValueError, match="Invalid DNS port"):
            ServerConfig(dns_port=0)

    def test_invalid_web_port(self):
        """Test invalid web port."""
        with pytest.raises(ValueError, match="Invalid web port"):
            ServerConfig(web_port=70000)

    def test_invalid_workers(self):
        """Test invalid workers count."""
        with pytest.raises(ValueError, match="Workers must be positive"):
            ServerConfig(workers=0)


class TestCacheConfig:
    """Test CacheConfig validation."""

    def test_valid_cache_config(self):
        """Test valid cache configuration."""
        config = CacheConfig(
            max_size_mb=100,
            default_ttl=300,
            min_ttl=1,
            max_ttl=86400,
            negative_ttl=300,
        )
        assert config.max_size_mb == 100
        assert config.default_ttl == 300

    def test_invalid_ttl_range(self):
        """Test invalid TTL range."""
        with pytest.raises(
            ValueError, match="Min TTL .* cannot be greater than max TTL"
        ):
            CacheConfig(min_ttl=100, max_ttl=50)

    def test_max_ttl_out_of_bounds(self):
        """Test max TTL out of bounds."""
        with pytest.raises(ValueError, match="Max TTL must be between 1 and 86400"):
            CacheConfig(max_ttl=100000)


class TestLoggingConfig:
    """Test LoggingConfig validation."""

    def test_valid_logging_config(self):
        """Test valid logging configuration."""
        config = LoggingConfig(
            level="INFO",
            format="json",
            file="logs/test.log",
            max_size_mb=50,
            backup_count=5,
        )
        assert config.level == "INFO"
        assert config.format == "json"

    def test_invalid_log_level(self):
        """Test invalid log level."""
        with pytest.raises(ValueError, match="Invalid log level"):
            LoggingConfig(level="INVALID")

    def test_invalid_log_format(self):
        """Test invalid log format."""
        with pytest.raises(ValueError, match="Invalid log format"):
            LoggingConfig(format="invalid")


class TestSecurityConfig:
    """Test SecurityConfig validation."""

    def test_valid_security_config(self):
        """Test valid security configuration."""
        config = SecurityConfig(
            rate_limit_per_ip=100,
            allowed_networks=["192.168.1.0/24", "10.0.0.0/8"],
            blacklist_enabled=True,
        )
        assert config.rate_limit_per_ip == 100
        assert len(config.allowed_networks) == 2

    def test_invalid_network(self):
        """Test invalid network in allowed_networks."""
        with pytest.raises(ValueError, match="Invalid network format"):
            SecurityConfig(allowed_networks=["invalid_network"])


class TestDNSConfig:
    """Test main DNSConfig validation."""

    def test_default_config(self):
        """Test default configuration creation."""
        config = create_default_config()
        assert isinstance(config, DNSConfig)
        assert config.server.bind_address == "127.0.0.1"
        assert len(config.upstream_servers) == 3

    def test_validate_config(self):
        """Test configuration validation."""
        config = create_default_config()
        assert validate_config(config) is True

    def test_no_upstream_servers(self):
        """Test configuration with no upstream servers."""
        with pytest.raises(
            ValueError, match="At least one upstream server must be configured"
        ):
            DNSConfig(upstream_servers=[])

    def test_invalid_upstream_server(self):
        """Test configuration with invalid upstream server."""
        with pytest.raises(ValueError, match="Invalid upstream server IP"):
            DNSConfig(upstream_servers=["invalid_ip"])

    def test_port_conflict(self):
        """Test DNS and web port conflict."""
        server_config = ServerConfig(dns_port=8080, web_port=8080)
        with pytest.raises(ValueError, match="DNS and web ports cannot be the same"):
            DNSConfig(server=server_config)
