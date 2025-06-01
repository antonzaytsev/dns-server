"""
Structured JSON Logging Framework

This module provides the core logging infrastructure using structlog for
structured JSON logging with multiple output destinations and filtering.
"""

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Optional

import structlog

from ..config.schema import LoggingConfig


class DualOutputLogger:
    """Logger that handles both console and file output with different formats."""

    def __init__(self, config: LoggingConfig):
        self.config = config
        self._configured = False
        self.console_logger = None
        self.file_logger = None

    def configure(self) -> None:
        """Configure dual output logging."""
        if self._configured:
            return

        # Configure console logger (human-readable)
        self._configure_console_logger()

        # Configure file logger (JSON) if file specified
        if self.config.file:
            self._configure_file_logger()

        # Configure structlog to use console format by default
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        self._configured = True

    def _configure_console_logger(self) -> None:
        """Configure console logger."""
        self.console_logger = logging.getLogger("console")
        self.console_logger.handlers.clear()
        self.console_logger.setLevel(getattr(logging, self.config.level.upper()))

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.config.level.upper()))

        # Simple formatter for console
        console_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)

        self.console_logger.addHandler(console_handler)

    def _configure_file_logger(self) -> None:
        """Configure file logger."""
        # Ensure log directory exists
        log_path = Path(self.config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        self.file_logger = logging.getLogger("file")
        self.file_logger.handlers.clear()
        self.file_logger.setLevel(getattr(logging, self.config.level.upper()))

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.config.file,
            maxBytes=self.config.max_size_mb * 1024 * 1024,
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, self.config.level.upper()))

        # JSON formatter for file
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
            )
        )

        self.file_logger.addHandler(file_handler)


class DetailedConsoleFormatter(logging.Formatter):
    """Custom formatter for console output with detailed error tracebacks."""

    def format(self, record):
        # Base format
        formatted = super().format(record)

        # Add detailed traceback for errors
        if record.exc_info:
            tb_lines = traceback.format_exception(*record.exc_info)
            traceback_str = "".join(tb_lines)
            formatted += f"\n{traceback_str}"

        return formatted


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
        """Configure structlog with proper dual output handling."""
        if self._configured:
            return

        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Set root logger level
        log_level = getattr(logging, self.config.level.upper())
        root_logger.setLevel(log_level)

        # Configure console handler only for now
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        # Use simple formatter to avoid structlog conflicts
        console_formatter = DetailedConsoleFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # Configure structlog processors
        processors = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure separate file logging if specified
        if self.config.file:
            self._setup_file_logging()

        self._configured = True
        self.logger = structlog.get_logger("dns_server")

    def _setup_file_logging(self) -> None:
        """Setup separate file logging with JSON format."""
        # Ensure log directory exists
        log_path = Path(self.config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create separate JSON logger for file output
        json_logger = logging.getLogger("json_file")
        json_logger.handlers.clear()
        json_logger.setLevel(getattr(logging, self.config.level.upper()))

        # Prevent propagation to avoid duplicate console output
        json_logger.propagate = False

        # File handler with JSON formatting
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.config.file,
            maxBytes=self.config.max_size_mb * 1024 * 1024,
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, self.config.level.upper()))

        # Custom JSON formatter that handles structured data
        class JSONFileFormatter(logging.Formatter):
            def format(self, record):
                # Extract structured data from the record
                log_dict = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }

                # Add any extra structured data
                if hasattr(record, "structured_data"):
                    log_dict.update(record.structured_data)

                # Add exception info if present
                if record.exc_info:
                    log_dict["exception"] = self.formatException(record.exc_info)

                import json

                return json.dumps(log_dict)

        file_handler.setFormatter(JSONFileFormatter())
        json_logger.addHandler(file_handler)

        # Store reference for use in logging calls
        self._json_logger = json_logger

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


def log_exception(
    logger: structlog.BoundLogger, message: str, exc: Exception = None
) -> None:
    """Log an exception with detailed traceback information.

    Args:
        logger: Logger instance
        message: Log message
        exc: Exception instance (optional, will use current exception if None)
    """
    if exc is None:
        # Get current exception info
        exc_info = sys.exc_info()
        if exc_info[1] is not None:
            exc = exc_info[1]

    if exc is not None:
        # Get detailed traceback
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        logger.error(
            message,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            traceback=tb_str,
            exc_info=True,
        )

        # Also log to JSON file if available
        if _logger_instance and hasattr(_logger_instance, "_json_logger"):
            json_logger = _logger_instance._json_logger
            json_record = logging.LogRecord(
                name=logger.name,
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg=message,
                args=(),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            json_record.structured_data = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": tb_str,
            }
            json_logger.handle(json_record)
    else:
        logger.error(message)
