"""
DNS Server Web Interface

This module provides the web interface server using aiohttp for:
- REST API endpoints for monitoring and control
- Static file serving for the dashboard
"""

import asyncio
import weakref
from pathlib import Path
from typing import Optional

from aiohttp import web
from aiohttp.web import Application

from ..config.schema import WebConfig
from ..dns_logging import get_logger, log_exception
from .api import setup_api_routes


class WebServer:
    """DNS Server Web Interface"""

    def __init__(self, config: WebConfig, dns_server_app):
        """Initialize web server.

        Args:
            config: Web configuration
            dns_server_app: Reference to main DNS server application
        """
        self.config = config
        self.dns_server_app = weakref.ref(
            dns_server_app
        )  # Weak reference to avoid circular references
        self.logger = get_logger("web_server")

        self.app: Optional[Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        self._shutdown_event = asyncio.Event()

    async def setup_application(self) -> Application:
        """Setup aiohttp application with routes and middleware."""
        app = web.Application()

        # Setup API routes (without WebSocket manager)
        setup_api_routes(app, self.dns_server_app)

        # Setup static file serving for frontend
        self._setup_static_routes(app)

        # Setup CORS for development
        self._setup_cors(app)

        # Add middleware
        app.middlewares.append(self._create_logging_middleware())
        app.middlewares.append(self._create_error_middleware())

        return app

    def _setup_static_routes(self, app: Application):
        """Setup static file serving."""
        # Determine static files path
        current_dir = Path(__file__).parent.parent.parent.parent  # Go to project root
        static_dir = current_dir / "web"

        if static_dir.exists():
            # Serve static files under /static/ path instead of root to avoid conflicts
            app.router.add_static("/static", path=static_dir, name="static")
            self.logger.info("Static files configured", path=str(static_dir))
        else:
            self.logger.warning(
                "Static files directory not found", path=str(static_dir)
            )

        # Serve index.html at root
        async def index_handler(request):
            index_file = static_dir / "index.html"
            if index_file.exists():
                return web.FileResponse(index_file)
            else:
                return web.Response(
                    text="<h1>DNS Server Web Interface</h1><p>Dashboard files not found</p>",
                    content_type="text/html",
                )

        # Add specific handler for root path
        app.router.add_get("/", index_handler)

        # Also handle common static file requests directly
        async def favicon_handler(request):
            favicon_file = static_dir / "favicon.ico"
            if favicon_file.exists():
                return web.FileResponse(favicon_file)
            else:
                return web.Response(status=404)

        app.router.add_get("/favicon.ico", favicon_handler)

        # Add handlers for CSS and JS files
        async def css_handler(request):
            filename = request.match_info["filename"]
            css_file = static_dir / "css" / filename
            if css_file.exists() and css_file.suffix == ".css":
                return web.FileResponse(css_file)
            else:
                return web.Response(status=404)

        async def js_handler(request):
            filename = request.match_info["filename"]
            js_file = static_dir / "js" / filename
            if js_file.exists() and js_file.suffix == ".js":
                return web.FileResponse(js_file)
            else:
                return web.Response(status=404)

        app.router.add_get("/css/{filename}", css_handler)
        app.router.add_get("/js/{filename}", js_handler)

    def _setup_cors(self, app: Application):
        """Setup CORS for development."""

        @web.middleware
        async def cors_handler(request, handler):
            response = await handler(request)

            # Add CORS headers
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization"
            )

            return response

        app.middlewares.append(cors_handler)

        # Handle OPTIONS requests
        async def options_handler(request):
            response = web.Response()
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization"
            )
            return response

        app.router.add_route("OPTIONS", "/{path:.*}", options_handler)

    def _create_logging_middleware(self):
        """Create logging middleware."""
        logger = self.logger

        @web.middleware
        async def logging_middleware(request, handler):
            """Log HTTP requests."""
            start_time = asyncio.get_event_loop().time()

            try:
                response = await handler(request)
                process_time = asyncio.get_event_loop().time() - start_time

                logger.info(
                    "HTTP request",
                    method=request.method,
                    path=request.path,
                    remote=request.remote,
                    status=response.status,
                    response_time_ms=round(process_time * 1000, 2),
                )

                return response

            except Exception as exc:
                process_time = asyncio.get_event_loop().time() - start_time

                # Use enhanced error logging with detailed traceback
                log_exception(
                    logger, f"HTTP request failed: {request.method} {request.path}", exc
                )

                # Also log basic request info
                logger.error(
                    "HTTP request failed",
                    method=request.method,
                    path=request.path,
                    remote=request.remote,
                    response_time_ms=round(process_time * 1000, 2),
                )
                raise

        return logging_middleware

    def _create_error_middleware(self):
        """Create error handling middleware."""
        logger = self.logger
        config = self.config

        @web.middleware
        async def error_middleware(request, handler):
            """Handle HTTP errors gracefully."""
            try:
                return await handler(request)
            except web.HTTPException:
                # Re-raise HTTP exceptions as they are handled properly by aiohttp
                raise
            except Exception as ex:
                # Use enhanced error logging with detailed traceback
                log_exception(
                    logger,
                    f"Unhandled error in web server: {request.method} {request.path}",
                    ex,
                )

                return web.json_response(
                    {
                        "error": "Internal server error",
                        "message": (
                            str(ex)
                            if getattr(config, "debug", False)
                            else "An unexpected error occurred"
                        ),
                    },
                    status=500,
                )

        return error_middleware

    async def start(self) -> None:
        """Start the web server."""
        if self.runner:
            self.logger.warning("Web server is already running")
            return

        try:
            # Setup application
            self.app = await self.setup_application()

            # Create runner
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            # Create site
            self.site = web.TCPSite(
                self.runner,
                host=getattr(self.config, "bind_address", "127.0.0.1"),
                port=getattr(self.config, "port", 9980),
            )

            await self.site.start()

            self.logger.info(
                "Web server started",
                host=getattr(self.config, "bind_address", "127.0.0.1"),
                port=getattr(self.config, "port", 9980),
            )

        except Exception as ex:
            self.logger.error("Failed to start web server", error=str(ex))
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the web server."""
        self.logger.info("Stopping web server")

        # Stop site
        if self.site:
            await self.site.stop()
            self.site = None

        # Cleanup runner
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

        self.app = None

        self.logger.info("Web server stopped")

    async def health_check(self) -> dict:
        """Get web server health status."""
        status = {
            "status": "healthy" if self.runner else "stopped",
        }

        return status
