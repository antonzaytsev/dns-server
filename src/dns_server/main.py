"""
DNS Server Main Entry Point

This script provides the main entry point for running the DNS server.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dns_server.cache import BasicDNSCache
from dns_server.config.loader import ConfigLoader
from dns_server.core import DNSServer

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

            logger.info("DNS server application initialized")

        except Exception as e:
            logger.error(f"Failed to initialize DNS server: {e}")
            raise

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
            logger.info("DNS server started successfully")

            # Setup signal handlers
            loop = asyncio.get_running_loop()
            for sig in [signal.SIGTERM, signal.SIGINT]:
                loop.add_signal_handler(sig, self._signal_handler)

            # Wait for shutdown signal
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"Error starting DNS server: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop the DNS server"""
        if self.dns_server:
            await self.dns_server.stop()
            logger.info("DNS server stopped")

    def _signal_handler(self):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    async def health_check(self):
        """Perform health check"""
        if self.dns_server:
            return await self.dns_server.health_check()
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

    args = parser.parse_args()

    app = DNSServerApp(args.config)

    if args.health_check:
        # Perform health check
        try:
            await app.initialize()
            health = await app.health_check()
            print(f"Health status: {health['status']}")
            sys.exit(0 if health["status"] == "healthy" else 1)
        except Exception as e:
            print(f"Health check failed: {e}")
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
