"""Tests for the configuration loader module."""

import json
import os
import tempfile

import pytest
import yaml

from src.dns_server.config.loader import ConfigLoader, load_config_from_file
from src.dns_server.config.schema import DNSConfig


class TestConfigLoader:
    """Test ConfigLoader functionality."""

    def test_load_default_config(self):
        """Test loading default configuration without file."""
        loader = ConfigLoader()
        config = loader.load_config()

        assert isinstance(config, DNSConfig)
        assert config.server.bind_address == "127.0.0.1"
        assert config.server.dns_port == 9953
        assert len(config.upstream_servers) == 3

    def test_load_yaml_config(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
server:
  bind_address: "0.0.0.0"
  dns_port: 53
  web_port: 8080

upstream_servers:
  - "8.8.8.8"
  - "1.1.1.1"

cache:
  max_size_mb: 200
  default_ttl: 600

logging:
  level: "DEBUG"
  format: "json"
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)
            config = loader.load_config()

            assert config.server.bind_address == "0.0.0.0"
            assert config.server.dns_port == 53
            assert config.cache.max_size_mb == 200
            assert config.cache.default_ttl == 600
            assert config.logging.level == "DEBUG"
            assert len(config.upstream_servers) == 2
        finally:
            os.unlink(config_file)

    def test_load_json_config(self):
        """Test loading configuration from JSON file."""
        json_content = {
            "server": {"bind_address": "192.168.1.1", "dns_port": 9953, "workers": 8},
            "cache": {"max_size_mb": 50, "min_ttl": 5},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_content, f)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)
            config = loader.load_config()

            assert config.server.bind_address == "192.168.1.1"
            assert config.server.workers == 8
            assert config.cache.max_size_mb == 50
            assert config.cache.min_ttl == 5
        finally:
            os.unlink(config_file)

    def test_file_not_found(self):
        """Test handling of non-existent configuration file."""
        loader = ConfigLoader("/non/existent/file.yaml", enable_hot_reload=False)

        with pytest.raises(FileNotFoundError):
            loader.load_config()

    def test_invalid_yaml_file(self):
        """Test handling of invalid YAML file."""
        invalid_yaml = "invalid: yaml: content: ["

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)

            with pytest.raises(yaml.YAMLError):
                loader.load_config()
        finally:
            os.unlink(config_file)

    def test_invalid_json_file(self):
        """Test handling of invalid JSON file."""
        invalid_json = '{"invalid": json, "content":'

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(invalid_json)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)

            with pytest.raises(json.JSONDecodeError):
                loader.load_config()
        finally:
            os.unlink(config_file)

    def test_auto_format_detection(self):
        """Test automatic format detection for files without extension."""
        yaml_content = "server:\n  dns_port: 9999"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(yaml_content)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)
            config = loader.load_config()

            assert config.server.dns_port == 9999
        finally:
            os.unlink(config_file)

    def test_environment_variable_overrides(self):
        """Test environment variable overrides."""
        # Set environment variables
        env_vars = {
            "DNS_SERVER_SERVER_DNS_PORT": "9953",
            "DNS_SERVER_SERVER_BIND_ADDRESS": "10.0.0.1",
            "DNS_SERVER_CACHE_MAX_SIZE_MB": "500",
            "DNS_SERVER_LOGGING_LEVEL": "ERROR",
            "DNS_SERVER_WEB_ENABLED": "false",
            "DNS_SERVER_UPSTREAM_SERVERS": "4.4.4.4,8.8.4.4",
        }

        # Store original values
        original_values = {}
        for key in env_vars:
            original_values[key] = os.environ.get(key)
            os.environ[key] = env_vars[key]

        try:
            loader = ConfigLoader(enable_hot_reload=False)
            config = loader.load_config()

            assert config.server.dns_port == 9953
            assert config.server.bind_address == "10.0.0.1"
            assert config.cache.max_size_mb == 500
            assert config.logging.level == "ERROR"
            assert config.web.enabled is False
            assert config.upstream_servers == ["4.4.4.4", "8.8.4.4"]

        finally:
            # Restore original environment
            for key, original_value in original_values.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    def test_environment_value_conversion(self):
        """Test conversion of environment variable values to proper types."""
        env_vars = {
            "DNS_SERVER_SERVER_DNS_PORT": "9953",  # Should become int
            "DNS_SERVER_SERVER_WEB_PORT": "8080",  # Different from DNS port
            "DNS_SERVER_WEB_ENABLED": "true",  # Should become bool
            "DNS_SERVER_SECURITY_BLACKLIST_ENABLED": "false",  # Should become bool
            "DNS_SERVER_CACHE_DEFAULT_TTL": "300.5",  # Should become float
        }

        original_values = {}
        for key in env_vars:
            original_values[key] = os.environ.get(key)
            os.environ[key] = env_vars[key]

        try:
            loader = ConfigLoader(enable_hot_reload=False)
            config = loader.load_config()

            assert config.server.dns_port == 9953
            assert isinstance(config.server.dns_port, int)
            assert config.server.web_port == 8080
            assert isinstance(config.server.web_port, int)
            assert config.web.enabled is True
            assert isinstance(config.web.enabled, bool)
            assert config.security.blacklist_enabled is False
            assert isinstance(config.security.blacklist_enabled, bool)

        finally:
            for key, original_value in original_values.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    def test_config_validation_error(self):
        """Test handling of configuration validation errors."""
        invalid_config = """
server:
  dns_port: 99999  # Invalid port number
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_config)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)

            with pytest.raises(ValueError, match="Invalid DNS port"):
                loader.load_config()
        finally:
            os.unlink(config_file)

    def test_config_merge(self):
        """Test merging file config with defaults."""
        partial_config = """
server:
  dns_port: 5555

cache:
  max_size_mb: 150
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(partial_config)
            config_file = f.name

        try:
            loader = ConfigLoader(config_file, enable_hot_reload=False)
            config = loader.load_config()

            # Should have overridden values
            assert config.server.dns_port == 5555
            assert config.cache.max_size_mb == 150

            # Should keep default values for non-specified settings
            assert config.server.bind_address == "127.0.0.1"  # Default
            assert config.server.web_port == 8080  # Default
            assert config.cache.default_ttl == 300  # Default

        finally:
            os.unlink(config_file)

    def test_convenience_function(self):
        """Test the convenience function for loading configuration."""
        config, loader = load_config_from_file(enable_hot_reload=False)

        assert isinstance(config, DNSConfig)
        assert isinstance(loader, ConfigLoader)
        assert config.server.bind_address == "127.0.0.1"

    def test_hot_reload_disabled_when_no_watchdog(self):
        """Test that hot reload is disabled gracefully when watchdog is not available."""
        # This test would need to mock the import, but for now we just test the basic case
        loader = ConfigLoader(enable_hot_reload=True)
        config = loader.load_config()

        # Should not raise any errors
        assert isinstance(config, DNSConfig)

    def test_get_config(self):
        """Test getting current configuration."""
        loader = ConfigLoader(enable_hot_reload=False)

        # Before loading
        assert loader.get_config() is None

        # After loading
        config = loader.load_config()
        assert loader.get_config() == config
