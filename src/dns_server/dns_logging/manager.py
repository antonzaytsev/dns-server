"""
Log Management System

This module provides log rotation, compression, and cleanup functionality
for the DNS server logging system.
"""

import asyncio
import gzip
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config.schema import LoggingConfig
from .logger import get_logger


class LogManager:
    """Manages log rotation, compression, and cleanup."""

    def __init__(self, config: LoggingConfig):
        """Initialize log manager.

        Args:
            config: Logging configuration
        """
        self.config = config
        self.logger = get_logger("log_manager")
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the log management background tasks."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("Log manager started")

    async def stop(self) -> None:
        """Stop the log management background tasks."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Log manager stopped")

    async def _cleanup_loop(self) -> None:
        """Background loop for log cleanup tasks."""
        while self._running:
            try:
                await self._perform_cleanup()
                # Run cleanup every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in log cleanup loop", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def _perform_cleanup(self) -> None:
        """Perform log cleanup tasks."""
        if not self.config.file:
            return

        log_path = Path(self.config.file)
        log_dir = log_path.parent

        if not log_dir.exists():
            return

        # Compress old log files
        await self._compress_old_logs(log_dir, log_path.name)

        # Clean up old compressed logs
        await self._cleanup_old_logs(log_dir, log_path.name)

        self.logger.debug("Log cleanup completed")

    async def _compress_old_logs(self, log_dir: Path, base_name: str) -> None:
        """Compress rotated log files.

        Args:
            log_dir: Directory containing log files
            base_name: Base name of log files
        """
        try:
            # Find rotated log files that aren't compressed yet
            rotated_files = []
            for file_path in log_dir.glob(f"{base_name}.*"):
                if not file_path.name.endswith(".gz") and file_path.name != base_name:
                    # Check if this is a rotated log file (has numeric suffix)
                    suffix = file_path.suffix.lstrip(".")
                    if suffix.isdigit():
                        rotated_files.append(file_path)

            # Compress each rotated file
            for file_path in rotated_files:
                await self._compress_file(file_path)

        except Exception as e:
            self.logger.error("Error compressing old logs", error=str(e))

    async def _compress_file(self, file_path: Path) -> None:
        """Compress a single log file.

        Args:
            file_path: Path to file to compress
        """
        compressed_path = file_path.with_suffix(file_path.suffix + ".gz")

        try:
            # Read original file and write compressed version
            with open(file_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)

            # Remove original file after successful compression
            file_path.unlink()

            self.logger.debug(
                "Compressed log file",
                original=str(file_path),
                compressed=str(compressed_path),
            )

        except Exception as e:
            self.logger.error(
                "Error compressing log file", file=str(file_path), error=str(e)
            )
            # Clean up partially created compressed file
            if compressed_path.exists():
                compressed_path.unlink()

    async def _cleanup_old_logs(self, log_dir: Path, base_name: str) -> None:
        """Clean up old log files beyond retention policy.

        Args:
            log_dir: Directory containing log files
            base_name: Base name of log files
        """
        try:
            # Find all log files (compressed and uncompressed)
            log_files = []

            # Include current log file
            current_log = log_dir / base_name
            if current_log.exists():
                log_files.append((current_log, current_log.stat().st_mtime))

            # Include rotated files
            for file_path in log_dir.glob(f"{base_name}.*"):
                if file_path.name != base_name:
                    log_files.append((file_path, file_path.stat().st_mtime))

            # Sort by modification time (newest first)
            log_files.sort(key=lambda x: x[1], reverse=True)

            # Keep only the configured number of backup files (plus current)
            files_to_keep = self.config.backup_count + 1
            files_to_delete = log_files[files_to_keep:]

            # Delete old files
            for file_path, _ in files_to_delete:
                try:
                    file_path.unlink()
                    self.logger.debug("Deleted old log file", file=str(file_path))
                except Exception as e:
                    self.logger.error(
                        "Error deleting old log file", file=str(file_path), error=str(e)
                    )

        except Exception as e:
            self.logger.error("Error cleaning up old logs", error=str(e))

    def rotate_logs_manually(self) -> None:
        """Manually trigger log rotation."""
        try:
            if not self.config.file:
                self.logger.warning("No log file configured for rotation")
                return

            log_path = Path(self.config.file)
            if not log_path.exists():
                self.logger.warning("Log file does not exist", file=str(log_path))
                return

            # Create backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = log_path.with_suffix(f".{timestamp}")

            # Rename current log file
            log_path.rename(backup_path)

            self.logger.info(
                "Log file rotated manually",
                original=str(log_path),
                backup=str(backup_path),
            )

        except Exception as e:
            self.logger.error("Error rotating logs manually", error=str(e))

    def get_log_stats(self) -> dict:
        """Get statistics about log files.

        Returns:
            Dictionary with log file statistics
        """
        stats = {
            "current_log_size_mb": 0,
            "total_log_size_mb": 0,
            "log_file_count": 0,
            "compressed_file_count": 0,
            "last_rotation": None,
        }

        try:
            if not self.config.file:
                return stats

            log_path = Path(self.config.file)
            log_dir = log_path.parent

            if not log_dir.exists():
                return stats

            total_size = 0
            file_count = 0
            compressed_count = 0
            last_rotation = None

            # Check current log file
            if log_path.exists():
                current_size = log_path.stat().st_size
                stats["current_log_size_mb"] = round(current_size / (1024 * 1024), 2)
                total_size += current_size
                file_count += 1

            # Check rotated files
            for file_path in log_dir.glob(f"{log_path.name}.*"):
                if file_path.name != log_path.name:
                    file_stat = file_path.stat()
                    total_size += file_stat.st_size
                    file_count += 1

                    if file_path.name.endswith(".gz"):
                        compressed_count += 1

                    # Track most recent rotation time
                    if last_rotation is None or file_stat.st_mtime > last_rotation:
                        last_rotation = file_stat.st_mtime

            stats["total_log_size_mb"] = round(total_size / (1024 * 1024), 2)
            stats["log_file_count"] = file_count
            stats["compressed_file_count"] = compressed_count

            if last_rotation:
                stats["last_rotation"] = datetime.fromtimestamp(
                    last_rotation
                ).isoformat()

        except Exception as e:
            self.logger.error("Error getting log statistics", error=str(e))

        return stats

    def validate_log_directory(self) -> bool:
        """Validate that the log directory is writable.

        Returns:
            True if directory is valid and writable
        """
        try:
            if not self.config.file:
                return False

            log_path = Path(self.config.file)
            log_dir = log_path.parent

            # Create directory if it doesn't exist
            log_dir.mkdir(parents=True, exist_ok=True)

            # Test write permissions
            test_file = log_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()

            return True

        except Exception as e:
            self.logger.error("Log directory validation failed", error=str(e))
            return False


# Global log manager instance
_log_manager: Optional[LogManager] = None


def get_log_manager() -> Optional[LogManager]:
    """Get the global log manager instance.

    Returns:
        Log manager instance or None if not initialized
    """
    return _log_manager


def setup_log_manager(config: LoggingConfig) -> LogManager:
    """Setup the global log manager.

    Args:
        config: Logging configuration

    Returns:
        Configured log manager instance
    """
    global _log_manager
    _log_manager = LogManager(config)
    return _log_manager


async def start_log_management(config: LoggingConfig) -> LogManager:
    """Start log management with the given configuration.

    Args:
        config: Logging configuration

    Returns:
        Started log manager instance
    """
    manager = setup_log_manager(config)
    await manager.start()
    return manager


async def stop_log_management() -> None:
    """Stop the global log manager."""
    if _log_manager:
        await _log_manager.stop()
