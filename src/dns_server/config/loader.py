"""Configuration loader for the DNS server.

This module handles loading configuration from files and environment variables,
with validation and hot reload capabilities.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import yaml

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from .schema import DNSConfig, create_default_config


class ConfigLoader:
    """Configuration loader with hot reload support."""

    def __init__(
        self,
        config_file: Optional[str] = None,
        enable_hot_reload: bool = True,
        reload_callback: Optional[Callable[[DNSConfig], None]] = None,
    ):
        """Initialize configuration loader.

        Args:
            config_file: Path to configuration file (YAML or JSON)
            enable_hot_reload: Enable file watching for hot reload
            reload_callback: Callback function called when config changes
        """
        self.config_file = config_file
        self.enable_hot_reload = enable_hot_reload and WATCHDOG_AVAILABLE
        self.reload_callback = reload_callback
        self._config: Optional[DNSConfig] = None
        self._observer: Optional[Observer] = None
        self._last_reload_time = 0.0

    def load_config(self) -> DNSConfig:
        """Load configuration from file and environment variables.

        Returns:
            Loaded and validated DNS configuration

        Raises:
            FileNotFoundError: If config file is specified but not found
            ValueError: If configuration is invalid
            yaml.YAMLError: If YAML parsing fails
            json.JSONDecodeError: If JSON parsing fails
        """
        # Start with default configuration
        config_dict = self._get_default_config_dict()

        # Load from file if specified
        if self.config_file:
            file_config = self._load_from_file(self.config_file)
            config_dict = self._merge_configs(config_dict, file_config)

        # Apply environment variable overrides
        config_dict = self._apply_env_overrides(config_dict)

        # Create and validate configuration
        self._config = self._dict_to_config(config_dict)

        return self._config

    def start_hot_reload(self) -> None:
        """Start file watching for hot reload."""
        if not self.enable_hot_reload or not self.config_file:
            return

        if not WATCHDOG_AVAILABLE:
            print("Warning: watchdog not available, hot reload disabled")
            return

        config_path = Path(self.config_file)
        if not config_path.exists():
            return

        event_handler = ConfigFileHandler(self._on_config_change)
        self._observer = Observer()
        self._observer.schedule(event_handler, str(config_path.parent), recursive=False)
        self._observer.start()

    def stop_hot_reload(self) -> None:
        """Stop file watching."""
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()

    def get_config(self) -> Optional[DNSConfig]:
        """Get current configuration."""
        return self._config

    def _load_from_file(self, file_path: str) -> Dict[str, Any]:
        """Load configuration from YAML or JSON file.

        Args:
            file_path: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If file is not found
            ValueError: If file format is not supported
            yaml.YAMLError: If YAML parsing fails
            json.JSONDecodeError: If JSON parsing fails
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Determine file format from extension
        if path.suffix.lower() in [".yaml", ".yml"]:
            result = yaml.safe_load(content)
            return result if isinstance(result, dict) else {}
        elif path.suffix.lower() == ".json":
            json_result = json.loads(content)
            return json_result if isinstance(json_result, dict) else {}
        else:
            # Try YAML first, then JSON
            try:
                result = yaml.safe_load(content)
                return result if isinstance(result, dict) else {}
            except yaml.YAMLError:
                try:
                    json_result = json.loads(content)
                    return json_result if isinstance(json_result, dict) else {}
                except json.JSONDecodeError:
                    raise ValueError(f"Unsupported file format: {file_path}")

    def _get_default_config_dict(self) -> Dict[str, Any]:
        """Get default configuration as dictionary."""
        default_config = create_default_config()
        return self._config_to_dict(default_config)

    def _config_to_dict(self, config: DNSConfig) -> Dict[str, Any]:
        """Convert configuration object to dictionary."""
        return {
            "server": {
                "bind_address": config.server.bind_address,
                "dns_port": config.server.dns_port,
                "web_port": config.server.web_port,
                "workers": config.server.workers,
                # Performance Optimization Settings
                "max_concurrent_requests": config.server.max_concurrent_requests,
                "request_queue_size": config.server.request_queue_size,
                "max_upstream_connections": config.server.max_upstream_connections,
                "connection_timeout": config.server.connection_timeout,
            },
            "upstream_servers": config.upstream_servers,
            "cache": {
                "max_size_mb": config.cache.max_size_mb,
                "default_ttl": config.cache.default_ttl,
                "min_ttl": config.cache.min_ttl,
                "max_ttl": config.cache.max_ttl,
                "negative_ttl": config.cache.negative_ttl,
            },
            "logging": {
                "level": config.logging.level,
                "format": config.logging.format,
                "file": config.logging.file,
                "max_size_mb": config.logging.max_size_mb,
                "backup_count": config.logging.backup_count,
            },
            "security": {
                "rate_limit_per_ip": config.security.rate_limit_per_ip,
                "allowed_networks": config.security.allowed_networks,
                "blacklist_enabled": config.security.blacklist_enabled,
            },
            "web": {
                "enabled": config.web.enabled,
                "real_time_updates": config.web.real_time_updates,
                "history_limit": config.web.history_limit,
            },
        }

    def _dict_to_config(self, config_dict: Dict[str, Any]) -> DNSConfig:
        """Convert dictionary to configuration object.

        Args:
            config_dict: Configuration dictionary

        Returns:
            DNS configuration object

        Raises:
            ValueError: If configuration is invalid
        """
        from .schema import (
            CacheConfig,
            LoggingConfig,
            SecurityConfig,
            ServerConfig,
            WebConfig,
        )

        # Create configuration objects with validation
        server_config = ServerConfig(**config_dict.get("server", {}))
        cache_config = CacheConfig(**config_dict.get("cache", {}))
        logging_config = LoggingConfig(**config_dict.get("logging", {}))
        security_config = SecurityConfig(**config_dict.get("security", {}))
        web_config = WebConfig(**config_dict.get("web", {}))

        config = DNSConfig(
            server=server_config,
            upstream_servers=config_dict.get("upstream_servers", []),
            cache=cache_config,
            logging=logging_config,
            security=security_config,
            web=web_config,
        )

        return config

    def _merge_configs(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge two configuration dictionaries.

        Args:
            base: Base configuration dictionary
            override: Override configuration dictionary

        Returns:
            Merged configuration dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_env_overrides(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration.

        Environment variables use the format DNS_SERVER_<SECTION>_<KEY>
        For example: DNS_SERVER_SERVER_DNS_PORT=9953

        Args:
            config_dict: Base configuration dictionary

        Returns:
            Configuration dictionary with environment overrides applied
        """
        env_prefix = "DNS_SERVER_"

        for env_key, env_value in os.environ.items():
            if not env_key.startswith(env_prefix):
                continue

            # Parse environment variable key
            key_parts = env_key[len(env_prefix) :].lower().split("_")
            if len(key_parts) < 2:
                continue

            section = key_parts[0]
            config_key = "_".join(key_parts[1:])

            # Convert value to appropriate type
            value = self._convert_env_value(env_value)

            # Apply override
            if section in config_dict:
                if isinstance(config_dict[section], dict):
                    config_dict[section][config_key] = value
                else:
                    config_dict[section] = value
            elif section == "upstream" and config_key == "servers":
                # Special case for upstream servers (comma-separated list)
                if isinstance(value, str):
                    config_dict["upstream_servers"] = [
                        s.strip() for s in value.split(",")
                    ]

        return config_dict

    def _convert_env_value(self, value: str) -> Any:
        """Convert environment variable value to appropriate Python type.

        Args:
            value: Environment variable value as string

        Returns:
            Converted value
        """
        # Try boolean
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        elif value.lower() in ("false", "no", "0", "off"):
            return False

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    def _on_config_change(self, file_path: str) -> None:
        """Handle configuration file change event.

        Args:
            file_path: Path to changed file
        """
        # Debounce rapid changes
        current_time = time.time()
        if current_time - self._last_reload_time < 1.0:  # 1 second debounce
            return
        self._last_reload_time = current_time

        try:
            # Reload configuration
            new_config = self.load_config()

            # Call reload callback if provided
            if self.reload_callback:
                self.reload_callback(new_config)

            print(f"Configuration reloaded from {file_path}")

        except Exception as e:
            print(f"Error reloading configuration: {e}")


if WATCHDOG_AVAILABLE:

    class ConfigFileHandler(FileSystemEventHandler):
        """File system event handler for configuration changes."""

        def __init__(self, callback: Callable[[str], None]):
            """Initialize handler.

            Args:
                callback: Function to call when config file changes
            """
            self.callback = callback

        def on_modified(self, event: Any) -> None:
            """Handle file modification event."""
            if not event.is_directory:
                self.callback(event.src_path)


def load_config_from_file(
    config_file: Optional[str] = None,
    enable_hot_reload: bool = True,
    reload_callback: Optional[Callable[[DNSConfig], None]] = None,
) -> Tuple[DNSConfig, ConfigLoader]:
    """Convenience function to load configuration.

    Args:
        config_file: Path to configuration file
        enable_hot_reload: Enable hot reload
        reload_callback: Callback for configuration changes

    Returns:
        Tuple of (loaded config, config loader instance)
    """
    loader = ConfigLoader(config_file, enable_hot_reload, reload_callback)
    config = loader.load_config()

    if enable_hot_reload:
        loader.start_hot_reload()

    return config, loader
