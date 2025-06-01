"""
DNS Server REST API

This module provides REST API endpoints for:
- Server health and statistics
- Cache performance metrics and management
- Query log history and filtering
- Configuration management
- Prometheus-compatible metrics
"""

import time
from datetime import datetime

from aiohttp import web
from aiohttp.web import Application, Request, Response

from ..dns_logging import get_log_manager, get_request_tracker


def setup_api_routes(app: Application, dns_server_app_ref, websocket_manager):
    """Setup all API routes.

    Args:
        app: aiohttp Application instance
        dns_server_app_ref: Weak reference to DNS server application
        websocket_manager: WebSocket manager for real-time updates
    """
    api = APIHandler(dns_server_app_ref, websocket_manager)

    # Server status and health
    app.router.add_get("/api/status", api.get_server_status)
    app.router.add_get("/api/health", api.get_health_check)

    # Cache management
    app.router.add_get("/api/cache/stats", api.get_cache_stats)
    app.router.add_post("/api/cache/flush", api.flush_cache)
    app.router.add_delete("/api/cache/clear", api.clear_cache)

    # Logs
    app.router.add_get("/api/logs", api.get_logs)
    app.router.add_get("/api/logs/recent", api.get_recent_logs)

    # Configuration
    app.router.add_get("/api/config", api.get_config)
    app.router.add_post("/api/config/reload", api.reload_config)

    # Metrics (Prometheus-compatible)
    app.router.add_get("/api/metrics", api.get_metrics)
    app.router.add_get("/metrics", api.get_prometheus_metrics)


class APIHandler:
    """Handles all API endpoints."""

    def __init__(self, dns_server_app_ref, websocket_manager):
        """Initialize API handler.

        Args:
            dns_server_app_ref: Weak reference to DNS server application
            websocket_manager: WebSocket manager for real-time updates
        """
        self.dns_server_app_ref = dns_server_app_ref
        self.websocket_manager = websocket_manager

    def get_dns_server_app(self):
        """Get DNS server application instance."""
        if self.dns_server_app_ref:
            return self.dns_server_app_ref()
        return None

    async def get_server_status(self, request: Request) -> Response:
        """Get comprehensive server status and statistics."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Get DNS server stats
            dns_stats = {}
            if dns_app.dns_server:
                dns_stats = dns_app.dns_server.get_stats()

            # Get cache stats
            cache_stats = {}
            if dns_app.cache and hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()

            # Get performance monitor stats
            performance_stats = {}
            if dns_app.dns_server and dns_app.dns_server.performance_monitor:
                performance_stats = dns_app.dns_server.performance_monitor.get_stats()

            # Get log manager stats
            log_stats = {}
            log_manager = get_log_manager()
            if log_manager:
                log_stats = log_manager.get_log_stats()

            # Compile comprehensive status
            status = {
                "server": {
                    "status": (
                        "running"
                        if dns_app.dns_server and dns_app.dns_server._is_running
                        else "stopped"
                    ),
                    "uptime_seconds": time.time()
                    - dns_stats.get("start_time", time.time()),
                    "version": "1.0.0",  # TODO: Get from package metadata
                    "config_file": dns_app.config_path,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                "dns": dns_stats,
                "cache": cache_stats,
                "performance": performance_stats,
                "logging": log_stats,
                "websocket": {
                    "connected_clients": (
                        self.websocket_manager.get_client_count()
                        if self.websocket_manager
                        else 0
                    )
                },
            }

            return web.json_response(status)

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get server status: {str(ex)}"}, status=500
            )

    async def get_health_check(self, request: Request) -> Response:
        """Get simple health check status."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"status": "unhealthy", "message": "DNS server not available"},
                    status=503,
                )

            health = await dns_app.health_check()

            return web.json_response(
                {
                    "status": health.get("status", "unknown"),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "checks": health,
                }
            )

        except Exception as ex:
            return web.json_response(
                {"status": "unhealthy", "message": f"Health check failed: {str(ex)}"},
                status=500,
            )

    async def get_cache_stats(self, request: Request) -> Response:
        """Get detailed cache statistics."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app or not dns_app.cache:
                return web.json_response({"error": "Cache not available"}, status=503)

            # Get cache stats
            cache_stats = {}
            if hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()

                # Get performance history if requested
                if request.query.get("include_history", "false").lower() == "true":
                    cache_stats[
                        "performance_history"
                    ] = await dns_app.cache.stats_manager.get_performance_history()

            return web.json_response(
                {"cache": cache_stats, "timestamp": datetime.utcnow().isoformat() + "Z"}
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get cache stats: {str(ex)}"}, status=500
            )

    async def flush_cache(self, request: Request) -> Response:
        """Flush cache (clear expired entries)."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app or not dns_app.cache:
                return web.json_response({"error": "Cache not available"}, status=503)

            # Get optional domain filter from request body
            body = {}
            if request.content_type == "application/json":
                body = await request.json()

            domain_filter = body.get("domain")
            record_type = body.get("type")

            # Perform cache flush
            if hasattr(dns_app.cache, "flush"):
                if domain_filter:
                    # Selective flush by domain
                    result = await dns_app.cache.flush(
                        domain=domain_filter, record_type=record_type
                    )
                else:
                    # Full flush of expired entries
                    result = await dns_app.cache.flush()

                # Notify WebSocket clients
                if self.websocket_manager:
                    await self.websocket_manager.broadcast(
                        {
                            "type": "cache_flushed",
                            "domain": domain_filter,
                            "record_type": record_type,
                            "entries_removed": result.get("entries_removed", 0),
                        }
                    )

                return web.json_response(
                    {
                        "success": True,
                        "message": "Cache flushed successfully",
                        "entries_removed": result.get("entries_removed", 0),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                )
            else:
                return web.json_response(
                    {"error": "Cache flush not supported"}, status=501
                )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to flush cache: {str(ex)}"}, status=500
            )

    async def clear_cache(self, request: Request) -> Response:
        """Clear entire cache."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app or not dns_app.cache:
                return web.json_response({"error": "Cache not available"}, status=503)

            # Clear cache
            if hasattr(dns_app.cache, "clear"):
                result = await dns_app.cache.clear()

                # Notify WebSocket clients
                if self.websocket_manager:
                    await self.websocket_manager.broadcast(
                        {
                            "type": "cache_cleared",
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        }
                    )

                return web.json_response(
                    {
                        "success": True,
                        "message": "Cache cleared successfully",
                        "entries_removed": result.get("entries_removed", 0),
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                )
            else:
                return web.json_response(
                    {"error": "Cache clear not supported"}, status=501
                )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to clear cache: {str(ex)}"}, status=500
            )

    async def get_logs(self, request: Request) -> Response:
        """Get DNS query logs with filtering."""
        try:
            # Parse query parameters
            limit = int(request.query.get("limit", 100))
            offset = int(request.query.get("offset", 0))
            domain_filter = request.query.get("domain")
            query_type = request.query.get("type")
            client_ip = request.query.get("client_ip")
            since = request.query.get("since")  # ISO timestamp
            cache_hit = request.query.get("cache_hit")  # 'true'/'false'

            # Limit the maximum number of logs to prevent abuse
            limit = min(limit, 1000)

            # Get request tracker
            request_tracker = get_request_tracker()
            if not request_tracker:
                return web.json_response(
                    {"error": "Request tracker not available"}, status=503
                )

            # Build filters
            filters = {}
            if domain_filter:
                filters["domain"] = domain_filter
            if query_type:
                filters["query_type"] = query_type.upper()
            if client_ip:
                filters["client_ip"] = client_ip
            if cache_hit is not None:
                filters["cache_hit"] = cache_hit.lower() == "true"
            if since:
                filters["since"] = since

            # Get logs (this would need to be implemented in the request tracker)
            logs = []
            if hasattr(request_tracker, "get_recent_requests"):
                logs = await request_tracker.get_recent_requests(
                    limit=limit, offset=offset, filters=filters
                )

            return web.json_response(
                {
                    "logs": logs,
                    "total": len(logs),
                    "limit": limit,
                    "offset": offset,
                    "filters": filters,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except ValueError as ex:
            return web.json_response(
                {"error": f"Invalid query parameters: {str(ex)}"}, status=400
            )
        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get logs: {str(ex)}"}, status=500
            )

    async def get_recent_logs(self, request: Request) -> Response:
        """Get recent DNS query logs (last 50)."""
        try:
            limit = int(request.query.get("limit", 50))
            limit = min(limit, 100)  # Max 100 for recent logs

            request_tracker = get_request_tracker()
            if not request_tracker:
                return web.json_response(
                    {"error": "Request tracker not available"}, status=503
                )

            # Get recent logs
            logs = []
            if hasattr(request_tracker, "get_recent_requests"):
                logs = await request_tracker.get_recent_requests(limit=limit)

            return web.json_response(
                {
                    "logs": logs,
                    "count": len(logs),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get recent logs: {str(ex)}"}, status=500
            )

    async def get_config(self, request: Request) -> Response:
        """Get current configuration (sanitized)."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Get configuration (sanitized for security)
            config_dict = {}
            if dns_app.config:
                # Convert config to dict and sanitize sensitive information
                config_dict = self._sanitize_config(dns_app.config)

            return web.json_response(
                {
                    "config": config_dict,
                    "config_file": dns_app.config_path,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get config: {str(ex)}"}, status=500
            )

    def _sanitize_config(self, config) -> dict:
        """Sanitize configuration for web API (remove sensitive data)."""
        # This is a simple implementation - you might want to use a more sophisticated approach
        config_dict = {}

        # Safe attributes to expose
        safe_attrs = ["server", "cache", "logging", "web", "upstream_servers"]

        for attr in safe_attrs:
            if hasattr(config, attr):
                value = getattr(config, attr)
                if hasattr(value, "__dict__"):
                    config_dict[attr] = {
                        k: v
                        for k, v in value.__dict__.items()
                        if not k.startswith("_")
                        and "password" not in k.lower()
                        and "secret" not in k.lower()
                    }
                else:
                    config_dict[attr] = value

        return config_dict

    async def reload_config(self, request: Request) -> Response:
        """Reload configuration from file."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Reload configuration (this would need to be implemented)
            # For now, return a placeholder response
            return web.json_response(
                {
                    "success": True,
                    "message": "Configuration reload not yet implemented",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to reload config: {str(ex)}"}, status=500
            )

    async def get_metrics(self, request: Request) -> Response:
        """Get metrics in JSON format."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Compile metrics from various sources
            metrics = {"dns_server": {}, "cache": {}, "performance": {}, "system": {}}

            # DNS server metrics
            if dns_app.dns_server:
                dns_stats = dns_app.dns_server.get_stats()
                metrics["dns_server"] = dns_stats

            # Cache metrics
            if dns_app.cache and hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()
                metrics["cache"] = cache_stats

            # Performance metrics
            if dns_app.dns_server and dns_app.dns_server.performance_monitor:
                perf_stats = dns_app.dns_server.performance_monitor.get_stats()
                metrics["performance"] = perf_stats

            # System metrics (basic)
            import psutil

            process = psutil.Process()
            metrics["system"] = {
                "cpu_percent": process.cpu_percent(),
                "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
                "open_files": len(process.open_files()),
                "connections": len(process.connections()),
            }

            return web.json_response(
                {"metrics": metrics, "timestamp": datetime.utcnow().isoformat() + "Z"}
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get metrics: {str(ex)}"}, status=500
            )

    async def get_prometheus_metrics(self, request: Request) -> Response:
        """Get metrics in Prometheus format."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.Response(
                    text="# DNS server not available\n", content_type="text/plain"
                )

            # Generate Prometheus metrics format
            lines = [
                "# HELP dns_queries_total Total number of DNS queries",
                "# TYPE dns_queries_total counter",
            ]

            # DNS server metrics
            if dns_app.dns_server:
                stats = dns_app.dns_server.get_stats()
                lines.extend(
                    [
                        f'dns_queries_total {stats.get("total_queries", 0)}',
                        f'dns_queries_udp_total {stats.get("udp_queries", 0)}',
                        f'dns_queries_tcp_total {stats.get("tcp_queries", 0)}',
                        f'dns_errors_total {stats.get("errors", 0)}',
                    ]
                )

            # Cache metrics
            if dns_app.cache and hasattr(dns_app.cache, "stats_manager"):
                cache_stats = await dns_app.cache.stats_manager.get_stats()
                lines.extend(
                    [
                        "# HELP dns_cache_hits_total Total cache hits",
                        "# TYPE dns_cache_hits_total counter",
                        f'dns_cache_hits_total {cache_stats.get("cache_hits", 0)}',
                        "# HELP dns_cache_misses_total Total cache misses",
                        "# TYPE dns_cache_misses_total counter",
                        f'dns_cache_misses_total {cache_stats.get("cache_misses", 0)}',
                        "# HELP dns_cache_hit_ratio Cache hit ratio",
                        "# TYPE dns_cache_hit_ratio gauge",
                        f'dns_cache_hit_ratio {cache_stats.get("hit_ratio", 0)}',
                    ]
                )

            metrics_text = "\n".join(lines) + "\n"

            return web.Response(
                text=metrics_text,
                content_type="text/plain; version=0.0.4; charset=utf-8",
            )

        except Exception as ex:
            return web.Response(
                text=f"# Error generating metrics: {str(ex)}\n",
                content_type="text/plain",
            )
