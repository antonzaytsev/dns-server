"""
Structured JSON Logging Framework

This module provides the core logging infrastructure using structlog for
structured JSON logging with multiple output destinations and filtering.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import List, Optional

import structlog
from structlog.types import Processor

from ..config.schema import LoggingConfig


class StructuredLogger:
    """Structured logger using structlog with JSON formatting."""

    def __init__(self, config: LoggingConfig):
        """Initialize structured logger.

        Args:
            config: Logging configuration
        """
        self.config = config
        self._configured = False
        self.logger = None

    def configure(self) -> None:
        """Configure structlog with JSON formatter and multiple outputs."""
        if self._configured:
            return

        # Configure processors
        processors = self._get_processors()

        # Configure structlog
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure standard library logging
        self._configure_stdlib_logging()

        self._configured = True
        self.logger = structlog.get_logger("dns_server")

    def _get_processors(self) -> list[Processor]:
        """Get list of processors for structlog."""
        processors = [
            # Add timestamp
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]

        if self.config.format.lower() == "json":
            # JSON output for structured logging
            processors.append(structlog.processors.JSONRenderer())
        else:
            # Human-readable output for development
            processors.extend(
                [
                    structlog.dev.ConsoleRenderer(colors=True),
                    structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
                ]
            )

        return processors

    def _configure_stdlib_logging(self) -> None:
        """Configure standard library logging handlers."""
        # Clear existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Set log level
        log_level = getattr(logging, self.config.level.upper())
        root_logger.setLevel(log_level)

        # Configure console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        if self.config.format.lower() == "json":
            # Use structlog processor for JSON format
            console_handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processor=structlog.processors.JSONRenderer(),
                )
            )
        else:
            # Use standard formatter for text format
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console_handler.setFormatter(formatter)

        root_logger.addHandler(console_handler)

        # Configure file handler if specified
        if self.config.file:
            self._configure_file_handler(root_logger, log_level)

    def _configure_file_handler(
        self, root_logger: logging.Logger, log_level: int
    ) -> None:
        """Configure rotating file handler.

        Args:
            root_logger: Root logger instance
            log_level: Log level to set
        """
        # Ensure log directory exists
        log_path = Path(self.config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.config.file,
            maxBytes=self.config.max_size_mb * 1024 * 1024,  # Convert MB to bytes
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)

        if self.config.format.lower() == "json":
            # Use structlog processor for JSON format
            file_handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processor=structlog.processors.JSONRenderer(),
                )
            )
        else:
            # Use standard formatter for text format
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)

    def get_logger(self, name: str = "dns_server") -> structlog.BoundLogger:
        """Get a structured logger instance.

        Args:
            name: Logger name

        Returns:
            Structured logger instance
        """
        if not self._configured:
            self.configure()

        return structlog.get_logger(name)


# Global logger instance
_logger_instance: Optional[StructuredLogger] = None


def setup_logging(config: LoggingConfig) -> None:
    """Setup global logging configuration.

    Args:
        config: Logging configuration
    """
    global _logger_instance
    _logger_instance = StructuredLogger(config)
    _logger_instance.configure()


def get_logger(name: str = "dns_server") -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name

    Returns:
        Structured logger instance

    Raises:
        RuntimeError: If logging hasn't been configured
    """
    if _logger_instance is None:
        raise RuntimeError("Logging not configured. Call setup_logging() first.")

    return _logger_instance.get_logger(name)


def configure_logger_for_module(module_name: str) -> structlog.BoundLogger:
    """Configure logger for a specific module.

    Args:
        module_name: Name of the module

    Returns:
        Configured logger for the module
    """
    return get_logger(module_name)
