"""
DNS Server Main Entry Point

This script provides the main entry point for running the DNS server.
"""

import asyncio
import platform
import signal
import sys
from pathlib import Path

# Try to use uvloop for better performance on Unix systems
try:
    if platform.system() != "Windows":
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        print("Using uvloop for enhanced async performance")
except ImportError:
    print("uvloop not available, using default event loop")

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
from dns_server.dns_logging import (
    get_logger,
    log_exception,
    setup_logging,
    start_log_management,
    stop_log_management,
)
from dns_server.web import WebServer


class DNSServerApp:
    """DNS Server Application"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or "config/default.yaml"
        self.config = None
        self.dns_server = None
        self.web_server = None
        self.cache = None
        self._shutdown_event = asyncio.Event()
        self.logger = None

    async def initialize(self):
        """Initialize the application"""
        try:
            # Load configuration
            config_loader = ConfigLoader(self.config_path)
            self.config = config_loader.load_config()

            # Setup structured logging first
            await self._setup_logging()

            self.logger.info("DNS server application initializing")

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

            # Create web server if enabled
            web_config = getattr(self.config, "web", None)
            if web_config and getattr(web_config, "enabled", True):
                # Create web config that includes server settings
                web_server_config = type(
                    "WebServerConfig",
                    (),
                    {
                        "bind_address": self.config.server.bind_address,
                        "port": self.config.server.web_port,
                        "debug": False,
                        **vars(web_config),
                    },
                )()

                self.web_server = WebServer(web_server_config, self)

            self.logger.info(
                "DNS server application initialized",
                cache_size_mb=(
                    getattr(cache_config, "max_size_mb", 100) if cache_config else 100
                ),
                dns_port=self.config.server.dns_port,
                web_port=self.config.server.web_port,
                web_enabled=web_config and getattr(web_config, "enabled", True),
                workers=self.config.server.workers,
            )

        except Exception as e:
            if self.logger:
                log_exception(self.logger, "Failed to initialize DNS server", e)
            else:
                print(f"Failed to initialize DNS server: {e}")
                import traceback

                traceback.print_exc()
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

            self.logger.info(
                "Performance settings configured",
                max_connections=max_connections,
                max_concurrent=max_concurrent,
                queue_size=queue_size,
                connection_timeout=connection_timeout,
            )

    async def _setup_logging(self):
        """Setup structured logging configuration"""
        log_config = getattr(self.config, "logging", None)
        if log_config:
            # Setup structured logging
            setup_logging(log_config)

            # Start log management
            await start_log_management(log_config)

            # Get logger for this module
            self.logger = get_logger("dns_server_app")

            self.logger.info(
                "Structured logging configured",
                level=log_config.level,
                format=log_config.format,
                file=log_config.file,
                max_size_mb=log_config.max_size_mb,
                backup_count=log_config.backup_count,
            )
        else:
            # Fallback to basic logging
            import logging

            logging.basicConfig(level=logging.INFO)
            self.logger = get_logger("dns_server_app")
            self.logger.warning("No logging configuration found, using defaults")

    async def start(self):
        """Start the DNS server"""
        if not self.dns_server:
            await self.initialize()

        try:
            await self.dns_server.start()

            # Start web server if enabled
            if self.web_server:
                await self.web_server.start()

            self.logger.info(
                "DNS server started successfully",
                bind_address=self.config.server.bind_address,
                dns_port=self.config.server.dns_port,
                web_port=self.config.server.web_port,
                web_enabled=self.web_server is not None,
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
            log_exception(self.logger, "Error starting DNS server", e)
            raise
        finally:
            await self.stop()

    async def _cleanup_loop(self):
        """Background cleanup task for connection pool and monitoring"""
        while True:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                await connection_pool.cleanup_old_connections()
                self.logger.debug("Performed connection pool cleanup")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_exception(self.logger, "Error in cleanup loop", e)

    async def stop(self):
        """Stop the DNS server"""
        self.logger.info("Shutting down DNS server")

        # Stop web server first
        if self.web_server:
            await self.web_server.stop()
            self.logger.info("Web server stopped")

        if self.dns_server:
            await self.dns_server.stop()
            self.logger.info("DNS server stopped")

        # Stop performance monitoring
        await performance_monitor.stop_monitoring()

        # Clean up connection pool
        await connection_pool.cleanup_old_connections()

        # Stop log management
        await stop_log_management()

        self.logger.info("DNS server application shutdown complete")

    def _signal_handler(self):
        """Handle shutdown signals"""
        self.logger.info("Received shutdown signal")
        self._shutdown_event.set()

    async def health_check(self):
        """Perform health check"""
        health = {"status": "not_running"}

        if self.dns_server:
            health = await self.dns_server.health_check()
            # Add performance metrics to health check
            health["performance"] = performance_monitor.get_stats()

            # Add logging stats if available
            from dns_server.dns_logging import get_log_manager

            log_manager = get_log_manager()
            if log_manager:
                health["logging"] = log_manager.get_log_stats()

            # Add web server health if available
            if self.web_server:
                health["web"] = await self.web_server.health_check()

        return health


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
            if "logging" in health:
                print(f"Logging stats: {health['logging']}")
            if "web" in health:
                print(f"Web server health: {health['web']}")
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
            print("\nReceived keyboard interrupt")
        except Exception as e:
            print(f"DNS server failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDNS server interrupted")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
