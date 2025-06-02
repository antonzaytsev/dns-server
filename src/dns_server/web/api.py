"""
DNS Server Web API

Provides REST API endpoints for:
- Server status and statistics  
- Query logs and history
- Configuration management
- Health monitoring
"""

import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp_cors
from aiohttp import web, ClientSession
from aiohttp.web import Request, Response

from ..dns_logging import get_request_tracker

# Import performance monitoring
from ..core.performance import performance_monitor


def setup_api_routes(app: web.Application, dns_server_app) -> None:
    """Setup API routes."""
    api = APIHandler()
    
    # Set the DNS server app reference
    api.set_dns_server_app(dns_server_app)

    # Server status and stats
    app.router.add_get("/api/status", api.get_server_status)
    app.router.add_get("/api/stats", api.get_detailed_stats)

    # Query logs and history
    app.router.add_get("/api/queries", api.get_query_logs)
    app.router.add_delete("/api/queries", api.clear_query_logs)

    # Configuration and health
    app.router.add_get("/api/config", api.get_server_config)
    app.router.add_get("/api/health", api.health_check)

    # Monitoring and metrics
    app.router.add_get("/api/metrics", api.get_metrics)
    app.router.add_get("/api/metrics/prometheus", api.get_prometheus_metrics)

    # Test connectivity
    app.router.add_post("/api/test", api.test_dns_query)


class APIHandler:
    """Handles all API endpoints."""

    def __init__(self):
        """Initialize API handler."""
        pass

    def get_dns_server_app(self):
        """Get DNS server application instance."""
        # Handle weak reference properly
        dns_app_ref = getattr(self, "_dns_server_app", None)
        if dns_app_ref:
            # If it's a weak reference, call it to get the actual object
            if hasattr(dns_app_ref, '__call__'):
                return dns_app_ref()
            else:
                return dns_app_ref
        return None

    def set_dns_server_app(self, dns_app):
        """Set DNS server application instance."""
        self._dns_server_app = dns_app

    async def get_server_status(self, request: Request) -> Response:
        """Get basic server status and statistics."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app or not dns_app.dns_server:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Get DNS server stats
            dns_stats = dns_app.dns_server.get_stats()

            # Get detailed request tracker stats
            request_tracker = get_request_tracker()
            tracker_stats = request_tracker.get_stats()

            # Merge query type statistics into dns_stats for chart compatibility
            dns_stats_with_query_types = dns_stats.copy()
            dns_stats_with_query_types.update(tracker_stats)

            return web.json_response(
                {
                    "server": {
                        "status": "running" if dns_stats["is_running"] else "stopped",
                        "uptime_seconds": dns_stats["uptime_seconds"],
                        "dns_port": dns_app.config.server.dns_port,
                        "web_port": dns_app.config.server.web_port,
                        "bind_address": dns_app.config.server.bind_address,
                    },
                    "dns": dns_stats_with_query_types,
                    "requests": tracker_stats,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get server status: {str(ex)}"}, status=500
            )

    async def get_detailed_stats(self, request: Request) -> Response:
        """Get detailed server statistics."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app or not dns_app.dns_server:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Get all available stats
            dns_stats = dns_app.dns_server.get_stats()
            request_tracker = get_request_tracker()
            tracker_stats = request_tracker.get_stats()

            # Get performance metrics if available
            performance_stats = {}
            if performance_monitor:
                performance_stats = performance_monitor.get_stats()

            return web.json_response(
                {
                    "dns": dns_stats,
                    "requests": tracker_stats,
                    "performance": performance_stats,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to get detailed stats: {str(ex)}"}, status=500
            )

    async def get_query_logs(self, request: Request) -> Response:
        """Get DNS query logs with filtering."""
        try:
            # Parse query parameters
            limit = int(request.query.get("limit", 100))
            offset = int(request.query.get("offset", 0))
            domain_filter = request.query.get("domain")
            query_type = request.query.get("type")
            client_ip = request.query.get("client_ip")
            since = request.query.get("since")  # ISO timestamp

            # Limit the maximum number of logs to prevent abuse
            limit = min(limit, 1000)

            # Get request tracker
            request_tracker = get_request_tracker()
            if not request_tracker:
                return web.json_response(
                    {"error": "Request tracker not available"}, status=503
                )

            # Get recent requests directly from the tracker
            logs = list(request_tracker.recent_requests)
            
            # Apply filters if provided
            if domain_filter:
                logs = [log for log in logs if domain_filter.lower() in log.get("domain", "").lower()]
            if query_type:
                logs = [log for log in logs if log.get("query_type") == query_type.upper()]
            if client_ip:
                logs = [log for log in logs if log.get("client_ip") == client_ip]
            if since:
                try:
                    since_time = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    logs = [log for log in logs 
                           if datetime.fromisoformat(log.get("timestamp", "").replace("Z", "+00:00")) >= since_time]
                except ValueError:
                    pass  # Skip invalid timestamp filter

            # Apply offset and limit
            total_count = len(logs)
            logs = logs[offset:offset + limit]

            return web.json_response(
                {
                    "logs": logs,
                    "total": total_count,
                    "count": len(logs),
                    "limit": limit,
                    "offset": offset,
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

    async def clear_query_logs(self, request: Request) -> Response:
        """Clear all DNS query logs."""
        try:
            # This is a placeholder implementation. In a real-world scenario,
            # you would implement this method to clear all query logs.
            return web.json_response(
                {"error": "Method not implemented"}, status=501
            )
        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to clear query logs: {str(ex)}"}, status=500
            )

    async def get_server_config(self, request: Request) -> Response:
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
        safe_attrs = ["server", "logging", "web", "upstream_servers", "security", "monitoring"]

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

    async def health_check(self, request: Request) -> Response:
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

    async def get_metrics(self, request: Request) -> Response:
        """Get metrics in JSON format."""
        try:
            dns_app = self.get_dns_server_app()
            if not dns_app:
                return web.json_response(
                    {"error": "DNS server not available"}, status=503
                )

            # Compile metrics from various sources
            metrics = {"dns_server": {}, "performance": {}, "system": {}}

            # DNS server metrics
            if dns_app.dns_server:
                dns_stats = dns_app.dns_server.get_stats()
                metrics["dns_server"] = dns_stats

            # Performance metrics
            if performance_monitor:
                perf_stats = performance_monitor.get_stats()
                metrics["performance"] = perf_stats

            # System metrics (basic)
            try:
                import psutil

                process = psutil.Process()
                metrics["system"] = {
                    "cpu_percent": process.cpu_percent(),
                    "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
                    "open_files": len(process.open_files()),
                    "connections": len(process.connections()),
                }
            except ImportError:
                metrics["system"] = {"error": "psutil not available"}

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
                        "# HELP dns_uptime_seconds Server uptime in seconds",
                        "# TYPE dns_uptime_seconds gauge",
                        f'dns_uptime_seconds {stats.get("uptime_seconds", 0)}',
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

    async def test_dns_query(self, request: Request) -> Response:
        """Test DNS query connectivity."""
        try:
            # This is a placeholder implementation. In a real-world scenario,
            # you would implement this method to test DNS query connectivity.
            return web.json_response(
                {"error": "Method not implemented"}, status=501
            )
        except Exception as ex:
            return web.json_response(
                {"error": f"Failed to test DNS query: {str(ex)}"}, status=500
            )
