"""
DNS Server Core

This module implements the main DNS server functionality including:
- Async UDP server using asyncio.DatagramProtocol
- Async TCP server using asyncio.StreamReader/StreamWriter
- Request routing and response handling
- Error handling and malformed packet rejection
- Performance monitoring and metrics
- Concurrency limiting and backpressure handling
"""

import asyncio
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .message import (
    DNSHeader,
    DNSMessage,
    DNSResponseCode,
)
from .performance import PerformanceMonitor, concurrency_limiter, timing_decorator
from .resolver import DNSResolver, IterativeResolver

# Import structured logging
from ..dns_logging import (
    get_logger,
    get_request_tracker,
    log_performance_event,
    log_security_event,
    format_response_data,
)

logger = get_logger("dns_server_core")


@dataclass
class RequestMetrics:
    """Metrics for a DNS request"""

    request_id: str
    client_ip: str
    start_time: float
    query_type: str
    domain: str
    protocol: str  # 'UDP' or 'TCP'

    def __post_init__(self):
        if not self.request_id:
            self.request_id = str(uuid.uuid4())


@dataclass
class ResponseMetrics:
    """Metrics for a DNS response"""

    response_code: str
    response_time_ms: float
    cache_hit: bool
    upstream_server: Optional[str]
    response_data: list
    answer_count: int


class DNSUDPProtocol(asyncio.DatagramProtocol):
    """Async UDP protocol handler for DNS queries"""

    def __init__(self, server: "DNSServer"):
        self.server = server
        self.transport = None

    def connection_made(self, transport):
        """Called when UDP socket is ready"""
        self.transport = transport
        logger.info(
            "DNS UDP server listening",
            address=transport.get_extra_info("sockname")[0],
            port=transport.get_extra_info("sockname")[1],
        )

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """Handle incoming UDP DNS queries"""
        client_ip = addr[0]

        # Create task to handle the request asynchronously
        task = asyncio.create_task(self._handle_request(data, client_ip, addr))

        # Store task reference to prevent garbage collection
        self.server._background_tasks.add(task)
        task.add_done_callback(self.server._background_tasks.discard)

    async def _handle_request(self, data: bytes, client_ip: str, addr: Tuple[str, int]):
        """Process DNS query and send response with concurrency limiting"""
        try:
            # Apply concurrency limiting
            async with await concurrency_limiter.acquire():
                response_data = await self.server.handle_dns_request(
                    data, client_ip, "UDP"
                )
                if response_data:
                    self.transport.sendto(response_data, addr)
        except RuntimeError as e:
            # Handle backpressure (queue full, etc.)
            logger.warning(
                "Request rejected due to backpressure",
                client_ip=client_ip,
                error=str(e),
            )
            # Log security event for potential DDoS
            log_security_event("backpressure_rejection", client_ip)
        except Exception as e:
            logger.error(
                "Error handling UDP request", client_ip=client_ip, error=str(e)
            )

    def error_received(self, exc):
        """Handle UDP errors"""
        logger.error("DNS UDP protocol error", error=str(exc))


class DNSServer:
    """Main DNS Server Implementation"""

    def __init__(self, config):
        self.config = config
        self.resolver = DNSResolver(config)
        self.iterative_resolver = IterativeResolver(self.resolver)
        self.cache = None  # Will be set externally
        self.performance_monitor = None  # Will be set externally

        # Get DNS request tracker
        self.request_tracker = get_request_tracker()

        # Server state
        self._udp_server = None
        self._tcp_server = None
        self._background_tasks = set()
        self._is_running = False

        # Performance tracking
        self._stats = {
            "total_queries": 0,
            "udp_queries": 0,
            "tcp_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "start_time": 0,
            "response_times": [],
        }

        # Rate limiting (per IP)
        self._rate_limits = {}

    def set_cache(self, cache):
        """Set the cache instance"""
        self.cache = cache
        self.resolver.set_cache(cache)

    def set_performance_monitor(self, monitor: PerformanceMonitor):
        """Set the performance monitor"""
        self.performance_monitor = monitor
        self.resolver.set_performance_monitor(monitor)

    async def start(self) -> None:
        """Start the DNS server (UDP and TCP)"""
        if self._is_running:
            logger.warning("Server is already running")
            return

        self._stats["start_time"] = time.time()

        bind_address = getattr(self.config.server, "bind_address", "127.0.0.1")
        dns_port = getattr(self.config.server, "dns_port", 5353)

        try:
            # Start UDP server
            loop = asyncio.get_running_loop()
            udp_transport, udp_protocol = await loop.create_datagram_endpoint(
                lambda: DNSUDPProtocol(self), local_addr=(bind_address, dns_port)
            )
            self._udp_server = (udp_transport, udp_protocol)

            # Start TCP server
            tcp_server = await asyncio.start_server(
                self._handle_tcp_client, host=bind_address, port=dns_port
            )
            self._tcp_server = tcp_server

            self._is_running = True
            logger.info(
                "DNS server started",
                bind_address=bind_address,
                dns_port=dns_port,
                protocol="UDP+TCP",
            )

        except Exception as e:
            logger.error("Failed to start DNS server", error=str(e))
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the DNS server"""
        if not self._is_running:
            return

        logger.info("Stopping DNS server")

        # Stop UDP server
        if self._udp_server:
            udp_transport, _ = self._udp_server
            udp_transport.close()

        # Stop TCP server
        if self._tcp_server:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()

        # Wait for background tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._is_running = False
        logger.info("DNS server stopped")

    async def _handle_tcp_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle TCP DNS client connection with concurrency limiting"""
        client_addr = writer.get_extra_info("peername")
        client_ip = client_addr[0] if client_addr else "unknown"

        try:
            # Apply concurrency limiting for TCP connections
            async with await concurrency_limiter.acquire():
                await self._process_tcp_connection(reader, writer, client_ip)
        except RuntimeError as e:
            logger.warning(
                "TCP connection rejected due to backpressure",
                client_ip=client_ip,
                error=str(e),
            )
            # Log security event for potential DDoS
            log_security_event("backpressure_rejection", client_ip)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_tcp_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, client_ip: str
    ):
        """Process TCP connection messages"""
        try:
            while True:
                # Read message length (2 bytes, network byte order)
                length_data = await reader.readexactly(2)
                if not length_data:
                    break

                message_length = struct.unpack("!H", length_data)[0]

                # Read the DNS message
                dns_data = await reader.readexactly(message_length)

                # Process the request
                response_data = await self.handle_dns_request(
                    dns_data, client_ip, "TCP"
                )

                if response_data:
                    # Send response with length prefix
                    response_length = struct.pack("!H", len(response_data))
                    writer.write(response_length + response_data)
                    await writer.drain()
                else:
                    # No response or error
                    break

        except asyncio.IncompleteReadError:
            # Client disconnected
            pass
        except Exception as e:
            logger.error("TCP client error", client_ip=client_ip, error=str(e))

    @timing_decorator("dns_request_handling", None)  # Will be set dynamically
    async def handle_dns_request(
        self, data: bytes, client_ip: str, protocol: str
    ) -> Optional[bytes]:
        """
        Main DNS request handler for both UDP and TCP
        """
        # Set up timing decorator with current performance monitor
        if self.performance_monitor:
            timing_decorator.__defaults__ = (
                "dns_request_handling",
                self.performance_monitor,
            )

        # Start request tracking
        request_id = self.request_tracker.start_request()
        start_time = time.time()

        try:
            # Parse DNS message
            try:
                query = DNSMessage.from_bytes(data)
            except Exception as e:
                logger.warning(
                    "Malformed DNS packet", client_ip=client_ip, error=str(e)
                )
                self._stats["errors"] += 1
                if self.performance_monitor:
                    self.performance_monitor.record_error("malformed_packet")

                # Log the error
                self.request_tracker.end_request(
                    request_id=request_id,
                    client_ip=client_ip,
                    query_type="UNKNOWN",
                    domain="UNKNOWN",
                    response_code="FORMERR",
                    cache_hit=False,
                    error="Malformed DNS packet",
                )

                return self._create_format_error_response(data)

            # Validate query
            if not query.is_query() or not query.questions:
                logger.warning("Invalid DNS query", client_ip=client_ip)
                self._stats["errors"] += 1
                if self.performance_monitor:
                    self.performance_monitor.record_error("invalid_query")

                # Log the error
                self.request_tracker.end_request(
                    request_id=request_id,
                    client_ip=client_ip,
                    query_type="UNKNOWN",
                    domain="UNKNOWN",
                    response_code="FORMERR",
                    cache_hit=False,
                    error="Invalid DNS query",
                )

                return self._create_format_error_response(data)

            # Get the first question
            question = query.questions[0]
            query_type = self._get_record_type_name(question.qtype)
            domain = question.name

            # Update stats
            self._stats["total_queries"] += 1
            if protocol == "UDP":
                self._stats["udp_queries"] += 1
            else:
                self._stats["tcp_queries"] += 1

            # Check rate limiting
            if not self._check_rate_limit(client_ip):
                logger.warning("Rate limit exceeded", client_ip=client_ip)
                if self.performance_monitor:
                    self.performance_monitor.record_error("rate_limit_exceeded")

                # Log security event
                log_security_event("rate_limit_exceeded", client_ip, domain)

                # Log the request
                self.request_tracker.end_request(
                    request_id=request_id,
                    client_ip=client_ip,
                    query_type=query_type,
                    domain=domain,
                    response_code="REFUSED",
                    cache_hit=False,
                    error="Rate limit exceeded",
                )

                response = query.create_response(DNSResponseCode.REFUSED)
                response.header.transaction_id = query.header.transaction_id
                return response.to_bytes()

            # Determine if recursion is desired and available
            recursion_desired = query.header.rd
            recursion_available = True  # We support recursion

            # Resolve the query
            cache_hit = False
            upstream_server = None
            response_data = []

            try:
                if recursion_desired and recursion_available:
                    # Check cache first
                    if self.cache:
                        cached = await self.cache.get(question)
                        if cached:
                            cache_hit = True
                            self._stats["cache_hits"] += 1
                            resolved_response = cached
                        else:
                            self._stats["cache_misses"] += 1
                            # Use recursive resolver
                            resolved_response = await self.resolver.resolve(
                                question, use_recursion=True
                            )
                            # Get upstream server info if available
                            upstream_server = getattr(
                                resolved_response, "upstream_server", None
                            )
                    else:
                        # Use recursive resolver without cache
                        resolved_response = await self.resolver.resolve(
                            question, use_recursion=True
                        )
                        upstream_server = getattr(
                            resolved_response, "upstream_server", None
                        )
                else:
                    # Use iterative resolver
                    resolved_response = await self.iterative_resolver.resolve(question)

                # Create response based on resolved data
                response = query.create_response(resolved_response.header.rcode)
                response.header.transaction_id = query.header.transaction_id
                response.header.ra = recursion_available

                # Copy answers from resolved response
                response.answers = resolved_response.answers
                response.authority = resolved_response.authority
                response.additional = resolved_response.additional

                # Format response data for logging
                response_data = format_response_data(response.answers, query_type)

            except Exception as e:
                logger.error("Resolution failed", domain=domain, error=str(e))
                if self.performance_monitor:
                    self.performance_monitor.record_error("resolution_failed")

                # Log the error
                self.request_tracker.end_request(
                    request_id=request_id,
                    client_ip=client_ip,
                    query_type=query_type,
                    domain=domain,
                    response_code="SERVFAIL",
                    cache_hit=False,
                    error=f"Resolution failed: {str(e)}",
                )

                response = query.create_response(DNSResponseCode.SERVFAIL)
                response.header.transaction_id = query.header.transaction_id
                response.header.ra = recursion_available

            # Calculate response time and update stats
            response_time_ms = (time.time() - start_time) * 1000
            self._stats["response_times"].append(response_time_ms)

            # Keep only last 1000 response times for memory efficiency
            if len(self._stats["response_times"]) > 1000:
                self._stats["response_times"] = self._stats["response_times"][-1000:]

            # Log the successful request
            response_code = self._get_response_code_name(response.header.rcode)
            self.request_tracker.end_request(
                request_id=request_id,
                client_ip=client_ip,
                query_type=query_type,
                domain=domain,
                response_code=response_code,
                cache_hit=cache_hit,
                upstream_server=upstream_server,
                response_data=response_data,
            )

            # Log performance event if slow
            if response_time_ms > 1000:  # Log slow queries (> 1 second)
                log_performance_event(
                    "slow_query",
                    response_time_ms,
                    domain=domain,
                    query_type=query_type,
                    client_ip=client_ip,
                )

            return response.to_bytes()

        except Exception as e:
            logger.error(
                "Unexpected error handling request", client_ip=client_ip, error=str(e)
            )
            self._stats["errors"] += 1
            if self.performance_monitor:
                self.performance_monitor.record_error("unexpected_error")

            # Log the error
            response_time_ms = (time.time() - start_time) * 1000
            self.request_tracker.end_request(
                request_id=request_id,
                client_ip=client_ip,
                query_type="UNKNOWN",
                domain="UNKNOWN",
                response_code="SERVFAIL",
                cache_hit=False,
                error=f"Unexpected error: {str(e)}",
            )

            # Try to create a SERVFAIL response
            try:
                # Parse original query to get transaction ID
                query = DNSMessage.from_bytes(data)
                response = query.create_response(DNSResponseCode.SERVFAIL)
                response.header.transaction_id = query.header.transaction_id
                return response.to_bytes()
            except:
                return None

    def _create_format_error_response(self, original_data: bytes) -> Optional[bytes]:
        """Create a format error response"""
        try:
            # Try to extract transaction ID from the original data
            if len(original_data) >= 2:
                transaction_id = struct.unpack("!H", original_data[:2])[0]
            else:
                transaction_id = 0

            # Create minimal FORMERR response
            header = DNSHeader(
                transaction_id=transaction_id,
                flags=0,
                qr=True,
                rcode=DNSResponseCode.FORMERR,
            )

            response = DNSMessage(
                header=header, questions=[], answers=[], authority=[], additional=[]
            )

            return response.to_bytes()
        except:
            return None

    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client IP is within rate limits"""
        rate_limit = getattr(self.config.security, "rate_limit_per_ip", 100)
        if rate_limit <= 0:
            return True  # No rate limiting

        current_time = time.time()

        # Clean old entries (older than 1 minute)
        self._rate_limits = {
            ip: times
            for ip, times in self._rate_limits.items()
            if times and max(times) > current_time - 60
        }

        # Check current IP
        if client_ip not in self._rate_limits:
            self._rate_limits[client_ip] = []

        # Remove times older than 1 minute
        self._rate_limits[client_ip] = [
            t for t in self._rate_limits[client_ip] if t > current_time - 60
        ]

        # Check if limit exceeded
        if len(self._rate_limits[client_ip]) >= rate_limit:
            return False

        # Add current request time
        self._rate_limits[client_ip].append(current_time)
        return True

    def _get_record_type_name(self, rtype: int) -> str:
        """Convert DNS record type to string"""
        type_names = {
            1: "A",
            28: "AAAA",
            5: "CNAME",
            15: "MX",
            2: "NS",
            12: "PTR",
            16: "TXT",
            6: "SOA",
            33: "SRV",
            99: "SPF",
        }
        return type_names.get(rtype, f"TYPE{rtype}")

    def _get_response_code_name(self, rcode: int) -> str:
        """Convert DNS response code to string"""
        code_names = {
            0: "NOERROR",
            1: "FORMERR",
            2: "SERVFAIL",
            3: "NXDOMAIN",
            4: "NOTIMP",
            5: "REFUSED",
        }
        return code_names.get(rcode, f"RCODE{rcode}")

    def get_stats(self) -> Dict[str, Any]:
        """Get server statistics"""
        uptime = (
            time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
        )

        stats = {
            "uptime_seconds": round(uptime, 2),
            "total_queries": self._stats["total_queries"],
            "udp_queries": self._stats["udp_queries"],
            "tcp_queries": self._stats["tcp_queries"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "errors": self._stats["errors"],
            "is_running": self._is_running,
        }

        # Calculate response time statistics
        if self._stats["response_times"]:
            response_times = self._stats["response_times"]
            stats.update(
                {
                    "avg_response_time_ms": round(
                        sum(response_times) / len(response_times), 2
                    ),
                    "min_response_time_ms": round(min(response_times), 2),
                    "max_response_time_ms": round(max(response_times), 2),
                }
            )

        # Calculate cache hit ratio
        total_cache_requests = stats["cache_hits"] + stats["cache_misses"]
        if total_cache_requests > 0:
            stats["cache_hit_ratio"] = round(
                stats["cache_hits"] / total_cache_requests, 3
            )
        else:
            stats["cache_hit_ratio"] = 0.0

        # Calculate queries per second
        if uptime > 0:
            stats["queries_per_second"] = round(stats["total_queries"] / uptime, 2)
        else:
            stats["queries_per_second"] = 0.0

        return stats

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        health = {
            "status": "healthy" if self._is_running else "stopped",
            "timestamp": time.time(),
            "uptime_seconds": time.time() - self._stats["start_time"]
            if self._stats["start_time"]
            else 0,
        }

        # Add basic stats
        health.update(self.get_stats())

        # Check resolver health
        if hasattr(self.resolver, "health_check"):
            resolver_health = await self.resolver.health_check()
            health["resolver"] = resolver_health

        # Check cache health
        if self.cache and hasattr(self.cache, "health_check"):
            cache_health = await self.cache.health_check()
            health["cache"] = cache_health

        return health
