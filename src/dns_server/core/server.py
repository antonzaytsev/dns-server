"""
DNS Server Core

This module implements the main DNS server functionality including:
- Async UDP server using asyncio.DatagramProtocol
- Async TCP server using asyncio.StreamReader/StreamWriter
- Request routing and response handling
- Error handling and malformed packet rejection
- Performance monitoring and metrics
"""

import asyncio
import logging
import socket
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .message import (
    DNSClass,
    DNSHeader,
    DNSMessage,
    DNSQuestion,
    DNSRecordType,
    DNSResponseCode,
)
from .resolver import DNSResolver, IterativeResolver

logger = logging.getLogger(__name__)


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
            f"DNS UDP server listening on {transport.get_extra_info('sockname')}"
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
        """Process DNS query and send response"""
        try:
            response_data = await self.server.handle_dns_request(data, client_ip, "UDP")
            if response_data:
                self.transport.sendto(response_data, addr)
        except Exception as e:
            logger.error(f"Error handling UDP request from {client_ip}: {e}")

    def error_received(self, exc):
        """Handle UDP errors"""
        logger.error(f"DNS UDP protocol error: {exc}")


class DNSServer:
    """Main DNS Server Implementation"""

    def __init__(self, config):
        self.config = config
        self.resolver = DNSResolver(config)
        self.iterative_resolver = IterativeResolver(self.resolver)
        self.cache = None  # Will be set externally

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
            logger.info(f"DNS server started on {bind_address}:{dns_port}")

        except Exception as e:
            logger.error(f"Failed to start DNS server: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the DNS server"""
        if not self._is_running:
            return

        logger.info("Stopping DNS server...")

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
        """Handle TCP DNS client connection"""
        client_addr = writer.get_extra_info("peername")
        client_ip = client_addr[0] if client_addr else "unknown"

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
            logger.error(f"TCP client error for {client_ip}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_dns_request(
        self, data: bytes, client_ip: str, protocol: str
    ) -> Optional[bytes]:
        """
        Main DNS request handler for both UDP and TCP
        """
        start_time = time.time()
        request_metrics = None
        response_metrics = None

        try:
            # Parse DNS message
            try:
                query = DNSMessage.from_bytes(data)
            except Exception as e:
                logger.warning(f"Malformed DNS packet from {client_ip}: {e}")
                self._stats["errors"] += 1
                return self._create_format_error_response(data)

            # Validate query
            if not query.is_query() or not query.questions:
                logger.warning(f"Invalid DNS query from {client_ip}")
                self._stats["errors"] += 1
                return self._create_format_error_response(data)

            # Get the first question
            question = query.questions[0]

            # Create request metrics
            request_metrics = RequestMetrics(
                request_id=str(uuid.uuid4()),
                client_ip=client_ip,
                start_time=start_time,
                query_type=self._get_record_type_name(question.qtype),
                domain=question.name,
                protocol=protocol,
            )

            # Update stats
            self._stats["total_queries"] += 1
            if protocol == "UDP":
                self._stats["udp_queries"] += 1
            else:
                self._stats["tcp_queries"] += 1

            # Check rate limiting
            if not self._check_rate_limit(client_ip):
                logger.warning(f"Rate limit exceeded for {client_ip}")
                response = query.create_response(DNSResponseCode.REFUSED)
                response.header.transaction_id = query.header.transaction_id
                return response.to_bytes()

            # Determine if recursion is desired and available
            recursion_desired = query.header.rd
            recursion_available = True  # We support recursion

            # Resolve the query
            cache_hit = False
            upstream_server = None

            try:
                if recursion_desired and recursion_available:
                    # Use recursive resolver
                    resolved_response = await self.resolver.resolve(
                        question, use_recursion=True
                    )

                    # Check if this was a cache hit
                    if self.cache:
                        cached = await self.cache.get(question)
                        if cached:
                            cache_hit = True
                            self._stats["cache_hits"] += 1
                        else:
                            self._stats["cache_misses"] += 1
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

            except Exception as e:
                logger.error(f"Resolution failed for {question.name}: {e}")
                response = query.create_response(DNSResponseCode.SERVFAIL)
                response.header.transaction_id = query.header.transaction_id
                response.header.ra = recursion_available

            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            self._stats["response_times"].append(response_time_ms)

            # Keep only last 1000 response times for memory efficiency
            if len(self._stats["response_times"]) > 1000:
                self._stats["response_times"] = self._stats["response_times"][-1000:]

            # Create response metrics
            response_data = []
            for answer in response.answers:
                response_data.append(answer.get_readable_rdata())

            response_metrics = ResponseMetrics(
                response_code=self._get_response_code_name(response.header.rcode),
                response_time_ms=response_time_ms,
                cache_hit=cache_hit,
                upstream_server=upstream_server,
                response_data=response_data,
                answer_count=len(response.answers),
            )

            # Log the request/response
            await self._log_dns_transaction(request_metrics, response_metrics)

            return response.to_bytes()

        except Exception as e:
            logger.error(f"Unexpected error handling request from {client_ip}: {e}")
            self._stats["errors"] += 1

            # Try to create a SERVFAIL response
            try:
                if request_metrics:
                    response_time_ms = (time.time() - start_time) * 1000
                    response_metrics = ResponseMetrics(
                        response_code="SERVFAIL",
                        response_time_ms=response_time_ms,
                        cache_hit=False,
                        upstream_server=None,
                        response_data=[],
                        answer_count=0,
                    )
                    await self._log_dns_transaction(request_metrics, response_metrics)

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

    async def _log_dns_transaction(
        self, request_metrics: RequestMetrics, response_metrics: ResponseMetrics
    ):
        """Log DNS transaction in structured JSON format"""
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
            "request_id": request_metrics.request_id,
            "client_ip": request_metrics.client_ip,
            "query_type": request_metrics.query_type,
            "domain": request_metrics.domain,
            "protocol": request_metrics.protocol,
            "response_code": response_metrics.response_code,
            "response_time_ms": round(response_metrics.response_time_ms, 2),
            "cache_hit": response_metrics.cache_hit,
            "upstream_server": response_metrics.upstream_server,
            "response_data": response_metrics.response_data,
            "answer_count": response_metrics.answer_count,
        }

        # Use structured logging if available
        logger.info("DNS query processed", extra={"dns_transaction": log_entry})

    def _get_record_type_name(self, rtype: int) -> str:
        """Get human-readable name for DNS record type"""
        type_map = {
            DNSRecordType.A: "A",
            DNSRecordType.AAAA: "AAAA",
            DNSRecordType.CNAME: "CNAME",
            DNSRecordType.MX: "MX",
            DNSRecordType.NS: "NS",
            DNSRecordType.PTR: "PTR",
            DNSRecordType.TXT: "TXT",
            DNSRecordType.SOA: "SOA",
            DNSRecordType.ANY: "ANY",
        }
        return type_map.get(rtype, f"TYPE{rtype}")

    def _get_response_code_name(self, rcode: int) -> str:
        """Get human-readable name for DNS response code"""
        code_map = {
            DNSResponseCode.NOERROR: "NOERROR",
            DNSResponseCode.FORMERR: "FORMERR",
            DNSResponseCode.SERVFAIL: "SERVFAIL",
            DNSResponseCode.NXDOMAIN: "NXDOMAIN",
            DNSResponseCode.NOTIMP: "NOTIMP",
            DNSResponseCode.REFUSED: "REFUSED",
        }
        return code_map.get(rcode, f"RCODE{rcode}")

    def get_stats(self) -> Dict[str, Any]:
        """Get server statistics"""
        uptime = (
            time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
        )

        response_times = self._stats["response_times"]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
            "uptime_seconds": round(uptime, 2),
            "total_queries": self._stats["total_queries"],
            "udp_queries": self._stats["udp_queries"],
            "tcp_queries": self._stats["tcp_queries"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "cache_hit_ratio": (
                self._stats["cache_hits"]
                / max(1, self._stats["cache_hits"] + self._stats["cache_misses"])
            ),
            "errors": self._stats["errors"],
            "avg_response_time_ms": round(avg_response_time, 2),
            "qps": (self._stats["total_queries"] / max(1, uptime) if uptime > 0 else 0),
            "is_running": self._is_running,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        health = {
            "status": "healthy",
            "server": self.get_stats(),
            "resolver": await self.resolver.health_check()
            if self.resolver
            else {"status": "unavailable"},
            "cache": await self.cache.get_stats()
            if self.cache
            else {"status": "unavailable"},
        }

        # Determine overall health
        if not self._is_running:
            health["status"] = "unhealthy"
        elif health["resolver"]["status"] == "degraded":
            health["status"] = "degraded"

        return health
