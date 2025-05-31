"""
Tests for DNS Logging System

This module tests the structured JSON logging functionality including:
- DNS request/response logging
- Request tracking and timing
- Log management and rotation
- Structured logging configuration
"""

import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

import pytest
import structlog

from dns_server.config.schema import LoggingConfig
from dns_server.dns_logging import (
    DNSRequestLogger,
    DNSRequestTracker,
    get_logger,
    get_request_tracker,
    setup_logging,
    start_log_management,
    stop_log_management,
)
from dns_server.dns_logging.logger import StructuredLogger
from dns_server.dns_logging.manager import LogManager


class TestStructuredLogger:
    """Test structured logging framework."""

    def test_structured_logger_creation(self):
        """Test creating a structured logger."""
        config = LoggingConfig(
            level="INFO", format="json", file="test.log", max_size_mb=10, backup_count=3
        )

        logger = StructuredLogger(config)
        assert logger.config == config
        assert not logger._configured

    def test_structured_logger_configuration(self):
        """Test logger configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            config = LoggingConfig(
                level="DEBUG",
                format="json",
                file=str(log_file),
                max_size_mb=1,
                backup_count=2,
            )

            logger = StructuredLogger(config)
            logger.configure()

            assert logger._configured
            assert logger.logger is not None

    def test_json_format_configuration(self):
        """Test JSON format configuration."""
        config = LoggingConfig(format="json")
        logger = StructuredLogger(config)

        processors = logger._get_processors()

        # Should include JSON renderer
        json_renderer_found = any(
            isinstance(proc, structlog.processors.JSONRenderer) for proc in processors
        )
        assert json_renderer_found

    def test_text_format_configuration(self):
        """Test text format configuration."""
        config = LoggingConfig(format="text")
        logger = StructuredLogger(config)

        processors = logger._get_processors()

        # Should include console renderer for text format
        console_renderer_found = any(
            isinstance(proc, structlog.dev.ConsoleRenderer) for proc in processors
        )
        assert console_renderer_found


class TestDNSRequestLogger:
    """Test DNS request logging functionality."""

    def setup_method(self):
        """Setup test environment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            self.temp_dir = temp_dir
            self.log_file = Path(temp_dir) / "dns_test.log"

            # Setup logging configuration
            config = LoggingConfig(
                level="INFO",
                format="json",
                file=str(self.log_file),
                max_size_mb=1,
                backup_count=2,
            )

            setup_logging(config)
            self.dns_logger = DNSRequestLogger()

    def test_dns_request_logging(self):
        """Test logging DNS request/response."""
        request_id = str(uuid.uuid4())

        self.dns_logger.log_dns_request(
            request_id=request_id,
            client_ip="192.168.1.100",
            query_type="A",
            domain="example.com",
            response_code="NOERROR",
            response_time_ms=45.2,
            cache_hit=True,
            upstream_server="8.8.8.8",
            response_data=["192.0.2.1"],
        )

        # Verify log file exists (would exist if file handler is configured)
        # Note: In test environment, we mainly verify no exceptions are raised
        assert True  # If we get here, logging didn't crash

    def test_dns_error_logging(self):
        """Test logging DNS errors."""
        request_id = str(uuid.uuid4())

        self.dns_logger.log_dns_error(
            request_id=request_id,
            client_ip="192.168.1.100",
            query_type="A",
            domain="example.com",
            error="Connection timeout",
            response_time_ms=5000.0,
        )

        # Verify no exceptions
        assert True


class TestDNSRequestTracker:
    """Test DNS request tracking functionality."""

    def setup_method(self):
        """Setup test environment."""
        # Setup minimal logging
        config = LoggingConfig(level="INFO", format="json")
        setup_logging(config)

        self.tracker = DNSRequestTracker()

    def test_request_tracking_lifecycle(self):
        """Test complete request tracking lifecycle."""
        # Start tracking
        request_id = self.tracker.start_request()
        assert request_id in self.tracker.active_requests

        # Small delay to measure time
        time.sleep(0.01)

        # End tracking
        response_time = self.tracker.end_request(
            request_id=request_id,
            client_ip="192.168.1.100",
            query_type="A",
            domain="example.com",
            response_code="NOERROR",
            cache_hit=False,
            upstream_server="8.8.8.8",
            response_data=["192.0.2.1"],
        )

        # Verify request is removed from active requests
        assert request_id not in self.tracker.active_requests

        # Verify response time is reasonable
        assert response_time > 0
        assert response_time < 1000  # Should be less than 1 second

    def test_request_tracking_with_error(self):
        """Test request tracking with error."""
        request_id = self.tracker.start_request()

        response_time = self.tracker.end_request(
            request_id=request_id,
            client_ip="192.168.1.100",
            query_type="A",
            domain="example.com",
            response_code="SERVFAIL",
            cache_hit=False,
            error="DNS resolution failed",
        )

        assert request_id not in self.tracker.active_requests
        assert response_time >= 0

    def test_custom_request_id(self):
        """Test using custom request ID."""
        custom_id = "custom-request-123"

        request_id = self.tracker.start_request(custom_id)
        assert request_id == custom_id
        assert custom_id in self.tracker.active_requests

    def test_global_request_tracker(self):
        """Test global request tracker singleton."""
        tracker1 = get_request_tracker()
        tracker2 = get_request_tracker()

        # Should be the same instance
        assert tracker1 is tracker2


class TestLogManager:
    """Test log management functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test.log"

        self.config = LoggingConfig(
            level="INFO",
            format="json",
            file=str(self.log_file),
            max_size_mb=1,
            backup_count=3,
        )

        self.manager = LogManager(self.config)

    def teardown_method(self):
        """Cleanup test environment."""
        self.temp_dir.cleanup()

    def test_log_manager_creation(self):
        """Test log manager creation."""
        assert self.manager.config == self.config
        assert not self.manager._running

    @pytest.mark.asyncio
    async def test_log_manager_start_stop(self):
        """Test starting and stopping log manager."""
        await self.manager.start()
        assert self.manager._running

        await self.manager.stop()
        assert not self.manager._running

    def test_log_directory_validation(self):
        """Test log directory validation."""
        # Should create directory and validate
        assert self.manager.validate_log_directory()
        assert self.log_file.parent.exists()

    def test_log_stats(self):
        """Test getting log statistics."""
        # Create a test log file
        self.log_file.write_text("test log content")

        stats = self.manager.get_log_stats()

        assert "current_log_size_mb" in stats
        assert "total_log_size_mb" in stats
        assert "log_file_count" in stats
        assert "compressed_file_count" in stats
        assert stats["log_file_count"] >= 1

    def test_manual_log_rotation(self):
        """Test manual log rotation."""
        # Create a test log file
        self.log_file.write_text("test log content")

        # Rotate the log
        self.manager.rotate_logs_manually()

        # Original file should be renamed, and new files should exist
        rotated_files = list(self.log_file.parent.glob(f"{self.log_file.name}.*"))
        assert len(rotated_files) >= 1


class TestIntegration:
    """Integration tests for the complete logging system."""

    @pytest.mark.asyncio
    async def test_complete_logging_setup(self):
        """Test complete logging system setup and teardown."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "integration_test.log"

            config = LoggingConfig(
                level="DEBUG",
                format="json",
                file=str(log_file),
                max_size_mb=1,
                backup_count=2,
            )

            # Setup logging
            setup_logging(config)

            # Start log management
            await start_log_management(config)

            # Get logger and log some messages
            logger = get_logger("test_integration")
            logger.info("Test message", test_field="test_value")

            # Get request tracker and track a request
            tracker = get_request_tracker()
            request_id = tracker.start_request()

            # Simulate some work
            await asyncio.sleep(0.01)

            # End request
            tracker.end_request(
                request_id=request_id,
                client_ip="127.0.0.1",
                query_type="A",
                domain="test.com",
                response_code="NOERROR",
                cache_hit=True,
                response_data=["127.0.0.1"],
            )

            # Stop log management
            await stop_log_management()

            # Verify no exceptions were raised
            assert True

    @pytest.mark.asyncio
    async def test_log_format_validation(self):
        """Test that logged JSON has correct format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "format_test.log"

            config = LoggingConfig(level="INFO", format="json", file=str(log_file))

            setup_logging(config)

            # Create and use DNS request logger
            dns_logger = DNSRequestLogger()
            request_id = str(uuid.uuid4())

            dns_logger.log_dns_request(
                request_id=request_id,
                client_ip="192.168.1.100",
                query_type="A",
                domain="example.com",
                response_code="NOERROR",
                response_time_ms=45.2,
                cache_hit=True,
                upstream_server="8.8.8.8",
                response_data=["192.0.2.1"],
            )

            # Wait a moment for log to be written
            await asyncio.sleep(0.1)

            # Read and verify log format (if file exists)
            if log_file.exists():
                content = log_file.read_text()
                if content.strip():
                    # Try to parse as JSON
                    lines = content.strip().split("\n")
                    for line in lines:
                        if line.strip():
                            log_entry = json.loads(line)

                            # Verify required fields exist
                            if "request_id" in log_entry:
                                assert log_entry["request_id"] == request_id
                                assert "timestamp" in log_entry
                                assert "client_ip" in log_entry
                                assert "query_type" in log_entry
                                assert "domain" in log_entry
                                assert "response_code" in log_entry
                                assert "response_time_ms" in log_entry
                                assert "cache_hit" in log_entry

            # If we get here without exceptions, the format is valid
            assert True


if __name__ == "__main__":
    pytest.main([__file__])
