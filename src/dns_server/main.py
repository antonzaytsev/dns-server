"""
DNS Server Main Entry Point

This script provides the main entry point for running the DNS server.
"""

import asyncio
import logging
import platform
import signal
import sys
from pathlib import Path

# Try to use uvloop for better performance on Unix systems
try:
    if platform.system() != "Windows":
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger = logging.getLogger(__name__)
        logger.info("Using uvloop for enhanced async performance")
except ImportError:
    logger = logging.getLogger(__name__)
    logger.info("uvloop not available, using default event loop")

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dns_server.cache import BasicDNSCache
from dns_server.config.loader import ConfigLoader
from dns_server.core import DNSServer
from dns_server.core.performance import (
    concurrency_limiter,
    connection_pool,
    performance_monitor,
)

logger = logging.getLogger(__name__)


class DNSServerApp:
    """DNS Server Application"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or "config/default.yaml"
        self.config = None
        self.dns_server = None
        self.cache = None
        self._shutdown_event = asyncio.Event()

    async def initialize(self):
        """Initialize the application"""
        try:
            # Load configuration
            config_loader = ConfigLoader(self.config_path)
            self.config = config_loader.load_config()

            # Setup logging
            self._setup_logging()

            # Initialize performance monitoring
            await performance_monitor.start_monitoring()

            # Configure connection pool and concurrency limiter based on config
            self._configure_performance_settings()

            # Create cache
            cache_config = getattr(self.config, "cache", None)
            cache_size = (
                getattr(cache_config, "max_size_mb", 100) * 1000
                if cache_config
                else 1000
            )
            self.cache = BasicDNSCache(max_size=cache_size)

            # Create DNS server
            self.dns_server = DNSServer(self.config)
            self.dns_server.set_cache(self.cache)

            # Set performance monitoring on DNS server
            self.dns_server.set_performance_monitor(performance_monitor)

            logger.info(
                "DNS server application initialized with performance optimizations"
            )

        except Exception as e:
            logger.error(f"Failed to initialize DNS server: {e}")
            raise

    def _configure_performance_settings(self):
        """Configure performance settings based on config"""
        # Configure connection pool
        server_config = getattr(self.config, "server", None)
        if server_config:
            max_connections = getattr(server_config, "max_upstream_connections", 100)
            connection_timeout = getattr(server_config, "connection_timeout", 30.0)

            # Update global connection pool settings
            connection_pool.max_connections = max_connections
            connection_pool.connection_timeout = connection_timeout

            # Configure concurrency limiter
            max_concurrent = getattr(server_config, "max_concurrent_requests", 1000)
            queue_size = getattr(server_config, "request_queue_size", 5000)

            concurrency_limiter.max_concurrent = max_concurrent
            concurrency_limiter.queue_size = queue_size
            concurrency_limiter._semaphore = asyncio.Semaphore(max_concurrent)
            concurrency_limiter._queue = asyncio.Queue(maxsize=queue_size)

            logger.info(
                f"Performance settings: max_connections={max_connections}, "
                f"max_concurrent={max_concurrent}, queue_size={queue_size}"
            )

    def _setup_logging(self):
        """Setup logging configuration"""
        log_config = getattr(self.config, "logging", None)
        if log_config:
            level = getattr(log_config, "level", "INFO")
            format_str = getattr(log_config, "format", "standard")

            if format_str == "json":
                # For structured logging, we'll use a simple format for now
                log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            else:
                log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

            logging.basicConfig(
                level=getattr(logging, level.upper()),
                format=log_format,
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        else:
            logging.basicConfig(level=logging.INFO)

    async def start(self):
        """Start the DNS server"""
        if not self.dns_server:
            await self.initialize()

        try:
            await self.dns_server.start()
            logger.info(
                "DNS server started successfully with performance optimizations"
            )

            # Setup signal handlers
            loop = asyncio.get_running_loop()
            for sig in [signal.SIGTERM, signal.SIGINT]:
                loop.add_signal_handler(sig, self._signal_handler)

            # Start background cleanup tasks
            cleanup_task = asyncio.create_task(self._cleanup_loop())

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            # Cancel cleanup task
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.error(f"Error starting DNS server: {e}")
            raise
        finally:
            await self.stop()

    async def _cleanup_loop(self):
        """Background cleanup task for connection pool and monitoring"""
        while True:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                await connection_pool.cleanup_old_connections()
                logger.debug("Performed connection pool cleanup")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def stop(self):
        """Stop the DNS server"""
        logger.info("Shutting down DNS server...")

        if self.dns_server:
            await self.dns_server.stop()
            logger.info("DNS server stopped")

        # Stop performance monitoring
        await performance_monitor.stop_monitoring()

        # Clean up connection pool
        await connection_pool.cleanup_old_connections()

        logger.info("DNS server application shutdown complete")

    def _signal_handler(self):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    async def health_check(self):
        """Perform health check"""
        if self.dns_server:
            health = await self.dns_server.health_check()
            # Add performance metrics to health check
            health["performance"] = performance_monitor.get_stats()
            return health
        return {"status": "not_running"}


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="DNS Server")
    parser.add_argument(
        "--config", "-c", default="config/default.yaml", help="Configuration file path"
    )
    parser.add_argument(
        "--health-check", action="store_true", help="Perform health check and exit"
    )
    parser.add_argument(
        "--performance-stats",
        action="store_true",
        help="Show performance statistics and exit",
    )

    args = parser.parse_args()

    app = DNSServerApp(args.config)

    if args.health_check:
        # Perform health check
        try:
            await app.initialize()
            health = await app.health_check()
            print(f"Health status: {health['status']}")
            if "performance" in health:
                print(f"Performance stats: {health['performance']}")
            sys.exit(0 if health["status"] == "healthy" else 1)
        except Exception as e:
            print(f"Health check failed: {e}")
            sys.exit(1)
    elif args.performance_stats:
        # Show performance statistics
        try:
            await app.initialize()
            await asyncio.sleep(1)  # Let monitoring collect some data
            stats = performance_monitor.get_stats()
            print("Performance Statistics:")
            for category, data in stats.items():
                print(f"  {category}: {data}")
            sys.exit(0)
        except Exception as e:
            print(f"Failed to get performance stats: {e}")
            sys.exit(1)
    else:
        # Start the server
        try:
            await app.start()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"DNS server failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDNS server interrupted")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
