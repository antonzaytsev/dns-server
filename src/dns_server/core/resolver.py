"""
DNS Resolver Engine

This module implements the core DNS resolution functionality including:
- Recursive resolution with connection pooling
- Iterative resolution
- Upstream forwarder with failover logic
- Root hints management
- Query timeout and retry mechanisms
- Performance optimization with connection pooling
"""

import asyncio
import logging
import random
import socket
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .message import (
    DNSClass,
    DNSHeader,
    DNSMessage,
    DNSQuestion,
    DNSRecordType,
    DNSResourceRecord,
    DNSResponseCode,
)
from .performance import PerformanceMonitor, connection_pool, timing_decorator

logger = logging.getLogger(__name__)


@dataclass
class UpstreamServer:
    """Upstream DNS server configuration"""

    address: str
    port: int = 53
    timeout: float = 5.0
    retries: int = 3
    is_available: bool = True
    last_failure: Optional[float] = None
    failure_count: int = 0


@dataclass
class QueryContext:
    """Context for a DNS query resolution"""

    original_question: DNSQuestion
    recursion_depth: int = 0
    max_recursion_depth: int = 10
    start_time: float = 0.0
    timeout: float = 30.0
    visited_servers: Set[str] = None

    def __post_init__(self):
        if self.visited_servers is None:
            self.visited_servers = set()
        if self.start_time == 0.0:
            self.start_time = time.time()

    def is_expired(self) -> bool:
        """Check if query has timed out"""
        return time.time() - self.start_time > self.timeout

    def can_recurse(self) -> bool:
        """Check if we can recurse further"""
        return self.recursion_depth < self.max_recursion_depth


class DNSResolver:
    """DNS Resolution Engine with performance optimizations"""

    # Root name servers (built-in root hints)
    ROOT_SERVERS = [
        "198.41.0.4",  # a.root-servers.net
        "170.247.170.2",  # b.root-servers.net
        "192.33.4.12",  # c.root-servers.net
        "199.7.91.13",  # d.root-servers.net
        "192.203.230.10",  # e.root-servers.net
        "192.5.5.241",  # f.root-servers.net
        "192.112.36.4",  # g.root-servers.net
        "198.97.190.53",  # h.root-servers.net
        "192.36.148.17",  # i.root-servers.net
        "192.58.128.30",  # j.root-servers.net
        "193.0.14.129",  # k.root-servers.net
        "199.7.83.42",  # l.root-servers.net
        "202.12.27.33",  # m.root-servers.net
    ]

    def __init__(self, config):
        self.config = config
        self.upstream_servers = self._load_upstream_servers(config.upstream_servers)
        self.cache = None  # Will be set by the server
        self.performance_monitor = None  # Will be set by the server
        self._transaction_counter = 0

    def _load_upstream_servers(
        self, server_addresses: List[str]
    ) -> List[UpstreamServer]:
        """Load upstream server configurations"""
        servers = []
        for addr in server_addresses:
            if ":" in addr:
                host, port = addr.rsplit(":", 1)
                port = int(port)
            else:
                host, port = addr, 53

            servers.append(
                UpstreamServer(
                    address=host,
                    port=port,
                    timeout=getattr(self.config, "upstream_timeout", 5.0),
                    retries=getattr(self.config, "upstream_retries", 3),
                )
            )

        return servers

    def set_cache(self, cache):
        """Set the cache instance"""
        self.cache = cache

    def set_performance_monitor(self, monitor: PerformanceMonitor):
        """Set the performance monitor"""
        self.performance_monitor = monitor

    @timing_decorator("dns_resolution", None)  # Will be set dynamically
    async def resolve(
        self, question: DNSQuestion, use_recursion: bool = True
    ) -> DNSMessage:
        """
        Main resolve method that routes queries to appropriate resolution strategy
        """
        # Set up timing decorator with current performance monitor
        if self.performance_monitor:
            timing_decorator.__defaults__ = ("dns_resolution", self.performance_monitor)

        context = QueryContext(original_question=question)

        try:
            # Check cache first if available
            if self.cache:
                cached_response = await self.cache.get(question)
                if cached_response:
                    logger.debug(f"Cache hit for {question.name} {question.qtype}")
                    if self.performance_monitor:
                        self.performance_monitor.record_operation_time(
                            "cache_lookup", 0.001
                        )
                    return cached_response

            # Determine resolution strategy
            if use_recursion and self.upstream_servers:
                # Forward to upstream servers
                response = await self._forward_to_upstream(question, context)
            else:
                # Perform recursive resolution ourselves
                response = await self._recursive_resolve(question, context)

            # Cache the response if we have a cache
            if (
                self.cache
                and response
                and response.header.rcode == DNSResponseCode.NOERROR
            ):
                await self.cache.put(question, response)

            return response

        except Exception as e:
            logger.error(f"Resolution failed for {question.name}: {e}")
            if self.performance_monitor:
                self.performance_monitor.record_error("dns_resolution_failed")
            # Return SERVFAIL response
            return self._create_error_response(question, DNSResponseCode.SERVFAIL)

    @timing_decorator("upstream_forwarding", None)
    async def _forward_to_upstream(
        self, question: DNSQuestion, context: QueryContext
    ) -> DNSMessage:
        """Forward query to upstream servers with failover and connection pooling"""
        # Set up timing decorator with current performance monitor
        if self.performance_monitor:
            timing_decorator.__defaults__ = (
                "upstream_forwarding",
                self.performance_monitor,
            )

        available_servers = [s for s in self.upstream_servers if s.is_available]
        if not available_servers:
            # Reset all servers if none are available
            for server in self.upstream_servers:
                server.is_available = True
                server.failure_count = 0
            available_servers = self.upstream_servers

        # Try servers in order, with some randomization
        random.shuffle(available_servers)

        for server in available_servers:
            try:
                response = await self._query_server_pooled(
                    server.address, server.port, question, server.timeout
                )

                # Reset failure count on success
                server.failure_count = 0
                server.last_failure = None

                return response

            except Exception as e:
                server.failure_count += 1
                server.last_failure = time.time()

                # Mark server as unavailable after multiple failures
                if server.failure_count >= server.retries:
                    server.is_available = False
                    logger.warning(
                        f"Marking upstream server {server.address} as unavailable"
                    )

                logger.debug(f"Upstream server {server.address} failed: {e}")
                continue

        # All upstream servers failed, try recursive resolution as fallback
        logger.warning(
            "All upstream servers failed, falling back to recursive resolution"
        )
        if self.performance_monitor:
            self.performance_monitor.record_error("all_upstream_servers_failed")
        return await self._recursive_resolve(question, context)

    @timing_decorator("recursive_resolution", None)
    async def _recursive_resolve(
        self, question: DNSQuestion, context: QueryContext
    ) -> DNSMessage:
        """Perform recursive DNS resolution starting from root servers"""
        # Set up timing decorator with current performance monitor
        if self.performance_monitor:
            timing_decorator.__defaults__ = (
                "recursive_resolution",
                self.performance_monitor,
            )

        if context.is_expired():
            logger.warning(f"Query for {question.name} timed out")
            if self.performance_monitor:
                self.performance_monitor.record_error("recursive_resolution_timeout")
            return self._create_error_response(question, DNSResponseCode.SERVFAIL)

        if not context.can_recurse():
            logger.warning(f"Maximum recursion depth reached for {question.name}")
            if self.performance_monitor:
                self.performance_monitor.record_error("max_recursion_depth_reached")
            return self._create_error_response(question, DNSResponseCode.SERVFAIL)

        # Start with root servers
        nameservers = self.ROOT_SERVERS.copy()

        while nameservers and not context.is_expired():
            # Try each nameserver for the current zone
            for ns_ip in nameservers:
                if ns_ip in context.visited_servers:
                    continue

                context.visited_servers.add(ns_ip)

                try:
                    response = await self._query_server_pooled(ns_ip, 53, question, 5.0)

                    # Check response code
                    if response.header.rcode == DNSResponseCode.NOERROR:
                        if response.answers:
                            # We got the answer!
                            return response
                        elif response.authority:
                            # We got a referral, extract nameservers
                            new_nameservers = []
                            ns_names = []

                            for auth_rr in response.authority:
                                if auth_rr.rtype == DNSRecordType.NS:
                                    ns_name = auth_rr.get_readable_rdata()
                                    ns_names.append(ns_name)

                            # Look for A records for the nameservers in additional section
                            for add_rr in response.additional:
                                if add_rr.rtype == DNSRecordType.A:
                                    ns_ip = add_rr.get_readable_rdata()
                                    if any(
                                        add_rr.name.startswith(ns_name.rstrip("."))
                                        for ns_name in ns_names
                                    ):
                                        new_nameservers.append(ns_ip)

                            # If we didn't get glue records, we need to resolve the NS names
                            if not new_nameservers and ns_names:
                                for ns_name in ns_names:
                                    if (
                                        ns_name != question.name
                                    ):  # Avoid infinite recursion
                                        try:
                                            ns_question = DNSQuestion(
                                                ns_name, DNSRecordType.A, DNSClass.IN
                                            )
                                            context.recursion_depth += 1
                                            ns_response = await self._recursive_resolve(
                                                ns_question, context
                                            )
                                            context.recursion_depth -= 1

                                            for answer in ns_response.answers:
                                                if answer.rtype == DNSRecordType.A:
                                                    new_nameservers.append(
                                                        answer.get_readable_rdata()
                                                    )
                                        except Exception:
                                            logger.debug(
                                                f"Failed to resolve nameserver {ns_name}"
                                            )

                            if new_nameservers:
                                nameservers = new_nameservers
                                break

                    elif response.header.rcode == DNSResponseCode.NXDOMAIN:
                        # Domain doesn't exist
                        return response

                except Exception as e:
                    logger.debug(f"Query to {ns_ip} failed: {e}")
                    continue

            # If we reach here, we need to move to the next set of nameservers
            break

        # Resolution failed
        if self.performance_monitor:
            self.performance_monitor.record_error("recursive_resolution_failed")
        return self._create_error_response(question, DNSResponseCode.SERVFAIL)

    async def _query_server_pooled(
        self, server_ip: str, port: int, question: DNSQuestion, timeout: float
    ) -> DNSMessage:
        """Send a DNS query to a specific server using connection pool"""
        start_time = time.time()

        try:
            # Try using connection pool first
            try:
                async with await connection_pool.get_connection(
                    server_ip, port
                ) as conn:
                    response = await self._send_query_with_connection(
                        conn, question, timeout
                    )

                    query_time = time.time() - start_time
                    if self.performance_monitor:
                        self.performance_monitor.record_operation_time(
                            "dns_query", query_time
                        )

                    return response

            except Exception as pool_error:
                # Log the pooled connection error and fall back to direct query
                logger.debug(
                    f"Pooled connection failed for {server_ip}:{port}, falling back to direct query: {pool_error}"
                )

                # Fallback to non-pooled query
                response = await self._query_server(server_ip, port, question, timeout)

                query_time = time.time() - start_time
                if self.performance_monitor:
                    self.performance_monitor.record_operation_time(
                        "dns_query_fallback", query_time
                    )

                return response

        except Exception as e:
            query_time = time.time() - start_time
            if self.performance_monitor:
                self.performance_monitor.record_operation_time(
                    "dns_query_failed", query_time
                )
                self.performance_monitor.record_error("dns_query_failed")
            raise e

    async def _send_query_with_connection(
        self, connection, question: DNSQuestion, timeout: float
    ) -> DNSMessage:
        """Send query using pooled connection - using UDP transport approach"""
        # Create query message
        self._transaction_counter = (self._transaction_counter + 1) % 65536
        header = DNSHeader(
            transaction_id=self._transaction_counter,
            flags=0,
            qr=False,
            rd=True,  # Recursion desired
            question_count=1,
        )

        query = DNSMessage(
            header=header, questions=[question], answers=[], authority=[], additional=[]
        )

        query_data = query.to_bytes()

        # Get server info from connection
        server = connection["server"]
        port = connection["port"]

        # Use the same UDP transport/protocol approach as fallback for consistency
        loop = asyncio.get_running_loop()

        # Create future for the response
        response_future = asyncio.Future()

        class DNSProtocol(asyncio.DatagramProtocol):
            def __init__(self, future):
                self.future = future

            def datagram_received(self, data, addr):
                if not self.future.done():
                    self.future.set_result(data)

            def error_received(self, exc):
                if not self.future.done():
                    self.future.set_exception(exc)

        try:
            # Create UDP endpoint
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: DNSProtocol(response_future), family=socket.AF_INET
            )

            try:
                # Send query
                transport.sendto(query_data, (server, port))

                # Wait for response with timeout
                try:
                    response_data = await asyncio.wait_for(
                        response_future, timeout=timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(
                        f"Query to {server}:{port} timed out after {timeout}s"
                    )

                # Parse response
                response = DNSMessage.from_bytes(response_data)

                # Verify transaction ID matches
                if response.header.transaction_id != header.transaction_id:
                    raise ValueError(
                        f"Transaction ID mismatch: expected {header.transaction_id}, got {response.header.transaction_id}"
                    )

                logger.debug(
                    f"Successful pooled DNS query to {server}:{port} for {question.name}"
                )
                return response

            finally:
                transport.close()

        except Exception as e:
            # Log the specific error for debugging
            logger.error(
                f"Pooled DNS query failed to {server}:{port}: {type(e).__name__}: {e}"
            )
            raise e

    async def _query_server(
        self, server_ip: str, port: int, question: DNSQuestion, timeout: float
    ) -> DNSMessage:
        """Send a DNS query to a specific server (fallback without pooling)"""

        # Create query message
        self._transaction_counter = (self._transaction_counter + 1) % 65536
        header = DNSHeader(
            transaction_id=self._transaction_counter,
            flags=0,
            qr=False,
            rd=True,  # Recursion desired
            question_count=1,
        )

        query = DNSMessage(
            header=header, questions=[question], answers=[], authority=[], additional=[]
        )

        query_data = query.to_bytes()

        # Use asyncio UDP transport/protocol instead of low-level socket operations
        loop = asyncio.get_running_loop()

        # Create future for the response
        response_future = asyncio.Future()

        class DNSProtocol(asyncio.DatagramProtocol):
            def __init__(self, future):
                self.future = future

            def datagram_received(self, data, addr):
                if not self.future.done():
                    self.future.set_result(data)

            def error_received(self, exc):
                if not self.future.done():
                    self.future.set_exception(exc)

        try:
            # Create UDP endpoint
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: DNSProtocol(response_future), family=socket.AF_INET
            )

            try:
                # Send query
                transport.sendto(query_data, (server_ip, port))

                # Wait for response with timeout
                try:
                    response_data = await asyncio.wait_for(
                        response_future, timeout=timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(
                        f"Query to {server_ip}:{port} timed out after {timeout}s"
                    )

                # Parse response
                response = DNSMessage.from_bytes(response_data)

                # Verify transaction ID matches
                if response.header.transaction_id != header.transaction_id:
                    raise ValueError(
                        f"Transaction ID mismatch: expected {header.transaction_id}, got {response.header.transaction_id}"
                    )

                logger.debug(
                    f"Successful DNS query to {server_ip}:{port} for {question.name}"
                )
                return response

            finally:
                transport.close()

        except Exception as e:
            logger.error(
                f"DNS query failed to {server_ip}:{port}: {type(e).__name__}: {e}"
            )
            raise e

    def _create_error_response(self, question: DNSQuestion, rcode: int) -> DNSMessage:
        """Create an error response for a question"""
        header = DNSHeader(
            transaction_id=0,  # Will be set by the server
            flags=0,
            qr=True,
            ra=True,
            rcode=rcode,
            question_count=1,
        )

        return DNSMessage(
            header=header, questions=[question], answers=[], authority=[], additional=[]
        )

    @timing_decorator("upstream_health_check", None)
    async def health_check(self) -> Dict[str, any]:
        """Check health of upstream servers and resolver"""
        # Set up timing decorator with current performance monitor
        if self.performance_monitor:
            timing_decorator.__defaults__ = (
                "upstream_health_check",
                self.performance_monitor,
            )

        health_info = {
            "status": "healthy",
            "upstream_servers": [],
            "root_servers_accessible": False,
        }

        # Check upstream servers
        for server in self.upstream_servers:
            server_health = {
                "address": f"{server.address}:{server.port}",
                "available": server.is_available,
                "failure_count": server.failure_count,
                "last_failure": server.last_failure,
            }

            # Test connectivity
            try:
                test_question = DNSQuestion("google.com.", DNSRecordType.A, DNSClass.IN)
                await self._query_server_pooled(
                    server.address, server.port, test_question, 3.0
                )
                server_health["responsive"] = True
                server_health["last_response_time"] = time.time()
            except Exception as e:
                server_health["responsive"] = False
                server_health["last_error"] = str(e)

            health_info["upstream_servers"].append(server_health)

        # Check root server accessibility
        try:
            root_server = random.choice(self.ROOT_SERVERS)
            test_question = DNSQuestion(".", DNSRecordType.NS, DNSClass.IN)
            await self._query_server_pooled(root_server, 53, test_question, 5.0)
            health_info["root_servers_accessible"] = True
        except Exception:
            health_info["root_servers_accessible"] = False
            health_info["status"] = "degraded"

        return health_info


class IterativeResolver:
    """Iterative DNS resolver for clients that don't want recursion"""

    def __init__(self, resolver: DNSResolver):
        self.resolver = resolver

    async def resolve(self, question: DNSQuestion) -> DNSMessage:
        """
        Perform iterative resolution - return referrals instead of recursing
        """
        # Check cache first
        if self.resolver.cache:
            cached_response = await self.resolver.cache.get(question)
            if cached_response:
                return cached_response

        # For iterative queries, we typically just check our cache and local data
        # If we don't have the answer, we return a referral to root servers

        # Create a referral response with root servers
        response_header = DNSHeader(
            transaction_id=0,  # Will be set by server
            flags=0,
            qr=True,
            aa=False,
            ra=False,  # Recursion not available for iterative queries
            rcode=DNSResponseCode.NOERROR,
        )

        response = DNSMessage(
            header=response_header,
            questions=[question],
            answers=[],
            authority=[],
            additional=[],
        )

        # Add root server NS records in authority section
        for i, root_ip in enumerate(self.resolver.ROOT_SERVERS[:3]):  # Just add a few
            root_name = f"{chr(ord('a') + i)}.root-servers.net."

            # NS record
            ns_record = DNSResourceRecord(
                name=".",
                rtype=DNSRecordType.NS,
                rclass=DNSClass.IN,
                ttl=86400,
                rdata=self._encode_name(root_name),
            )
            response.authority.append(ns_record)

            # A record in additional section
            a_record = DNSResourceRecord(
                name=root_name,
                rtype=DNSRecordType.A,
                rclass=DNSClass.IN,
                ttl=86400,
                rdata=socket.inet_aton(root_ip),
            )
            response.additional.append(a_record)

        return response

    def _encode_name(self, name: str) -> bytes:
        """Encode domain name for DNS records"""
        if name == ".":
            return b"\x00"

        labels = name.rstrip(".").split(".")
        result = b""
        for label in labels:
            label_bytes = label.encode("ascii")
            result += bytes([len(label_bytes)]) + label_bytes
        result += b"\x00"
        return result
