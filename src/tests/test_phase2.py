"""
Phase 2 Tests - Core DNS Engine

Basic tests to validate the DNS message parsing, resolver, and server functionality.
"""

import asyncio
import socket
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dns_server.cache.engine import BasicDNSCache
from dns_server.core.message import (
    DNSClass,
    DNSHeader,
    DNSMessage,
    DNSQuestion,
    DNSRecordType,
    DNSResourceRecord,
    DNSResponseCode,
    create_a_record,
    create_aaaa_record,
)
from dns_server.core.resolver import DNSResolver, UpstreamServer
from dns_server.core.server import DNSServer


class TestDNSMessage:
    """Test DNS message parsing and construction"""

    def test_dns_header_creation(self):
        """Test DNS header creation and flag handling"""
        header = DNSHeader(
            transaction_id=12345,
            flags=0,
            qr=True,
            rd=True,
            ra=True,
            rcode=DNSResponseCode.NOERROR,
            question_count=1,
        )

        assert header.transaction_id == 12345
        assert header.qr == True
        assert header.rd == True
        assert header.ra == True
        assert header.rcode == DNSResponseCode.NOERROR

    def test_dns_question_encoding(self):
        """Test DNS question encoding"""
        question = DNSQuestion("example.com.", DNSRecordType.A, DNSClass.IN)

        data = question.to_bytes()
        assert len(data) > 0

        # Test parsing back
        parsed_question, offset = DNSQuestion.parse(data, 0)
        assert parsed_question.name == "example.com."
        assert parsed_question.qtype == DNSRecordType.A
        assert parsed_question.qclass == DNSClass.IN

    def test_a_record_creation(self):
        """Test A record creation"""
        record = create_a_record("test.com.", "192.168.1.1", 300)

        assert record.name == "test.com."
        assert record.rtype == DNSRecordType.A
        assert record.ttl == 300
        assert record.get_readable_rdata() == "192.168.1.1"

    def test_aaaa_record_creation(self):
        """Test AAAA record creation"""
        record = create_aaaa_record("test.com.", "2001:db8::1", 300)

        assert record.name == "test.com."
        assert record.rtype == DNSRecordType.AAAA
        assert record.ttl == 300
        assert record.get_readable_rdata() == "2001:db8::1"

    def test_dns_message_roundtrip(self):
        """Test complete DNS message encoding and parsing"""
        # Create a query
        header = DNSHeader(
            transaction_id=54321, flags=0, qr=False, rd=True, question_count=1
        )

        question = DNSQuestion("google.com.", DNSRecordType.A, DNSClass.IN)

        message = DNSMessage(
            header=header, questions=[question], answers=[], authority=[], additional=[]
        )

        # Encode to bytes
        data = message.to_bytes()
        assert len(data) > 12  # Header + question

        # Parse back
        parsed_message = DNSMessage.from_bytes(data)

        assert parsed_message.header.transaction_id == 54321
        assert parsed_message.header.qr == False
        assert parsed_message.header.rd == True
        assert len(parsed_message.questions) == 1
        assert parsed_message.questions[0].name == "google.com."
        assert parsed_message.questions[0].qtype == DNSRecordType.A


class TestDNSCache:
    """Test basic DNS caching functionality"""

    @pytest.mark.asyncio
    async def test_cache_put_get(self):
        """Test basic cache put and get operations"""
        cache = BasicDNSCache(max_size=10)

        question = DNSQuestion("example.com.", DNSRecordType.A, DNSClass.IN)

        # Create a response
        header = DNSHeader(transaction_id=1, flags=0, qr=True)
        answer = create_a_record("example.com.", "192.168.1.1", 300)
        response = DNSMessage(
            header=header,
            questions=[question],
            answers=[answer],
            authority=[],
            additional=[],
        )

        # Cache miss initially
        cached = await cache.get(question)
        assert cached is None

        # Put in cache
        await cache.put(question, response)

        # Cache hit
        cached = await cache.get(question)
        assert cached is not None
        assert len(cached.answers) == 1
        assert cached.answers[0].get_readable_rdata() == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics"""
        cache = BasicDNSCache(max_size=5)
        stats = await cache.get_stats()

        assert stats["entries"] == 0
        assert stats["max_size"] == 5
        assert stats["status"] == "available"


class TestDNSResolver:
    """Test DNS resolver functionality"""

    def test_upstream_server_loading(self):
        """Test loading upstream server configuration"""
        config = Mock()
        config.upstream_servers = ["8.8.8.8", "1.1.1.1:53", "208.67.222.222:5353"]

        resolver = DNSResolver(config)

        assert len(resolver.upstream_servers) == 3
        assert resolver.upstream_servers[0].address == "8.8.8.8"
        assert resolver.upstream_servers[0].port == 53
        assert resolver.upstream_servers[2].port == 5353

    @pytest.mark.asyncio
    async def test_resolver_error_response(self):
        """Test error response creation"""
        config = Mock()
        config.upstream_servers = []

        resolver = DNSResolver(config)
        question = DNSQuestion("nonexistent.test.", DNSRecordType.A, DNSClass.IN)

        response = resolver._create_error_response(question, DNSResponseCode.SERVFAIL)

        assert response.header.qr == True
        assert response.header.rcode == DNSResponseCode.SERVFAIL
        assert len(response.questions) == 1
        assert response.questions[0].name == "nonexistent.test."


class TestDNSServer:
    """Test DNS server functionality"""

    def test_dns_server_creation(self):
        """Test DNS server initialization"""
        config = Mock()
        config.upstream_servers = ["8.8.8.8"]

        server = DNSServer(config)

        assert server.config == config
        assert server.resolver is not None
        assert server.iterative_resolver is not None
        assert server._is_running == False

    def test_server_stats(self):
        """Test server statistics"""
        config = Mock()
        config.upstream_servers = ["8.8.8.8"]

        server = DNSServer(config)
        stats = server.get_stats()

        assert "total_queries" in stats
        assert "udp_queries" in stats
        assert "tcp_queries" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "errors" in stats
        assert "is_running" in stats
        assert stats["is_running"] == False

    @pytest.mark.asyncio
    async def test_malformed_packet_handling(self):
        """Test handling of malformed DNS packets"""
        config = Mock()
        config.upstream_servers = ["8.8.8.8"]
        config.security = Mock()
        config.security.rate_limit_per_ip = 100

        server = DNSServer(config)

        # Test with completely invalid data
        response_data = await server.handle_dns_request(b"invalid", "127.0.0.1", "UDP")

        # Should get a format error response
        assert response_data is not None
        assert len(response_data) >= 12  # At least a DNS header

    def test_rate_limiting(self):
        """Test basic rate limiting functionality"""
        config = Mock()
        config.upstream_servers = ["8.8.8.8"]
        config.security = Mock()
        config.security.rate_limit_per_ip = 2  # Very low limit for testing

        server = DNSServer(config)

        # First two requests should pass
        assert server._check_rate_limit("192.168.1.1") == True
        assert server._check_rate_limit("192.168.1.1") == True

        # Third request should be rate limited
        assert server._check_rate_limit("192.168.1.1") == False

        # Different IP should still work
        assert server._check_rate_limit("192.168.1.2") == True


def test_record_type_names():
    """Test DNS record type name mapping"""
    config = Mock()
    config.upstream_servers = []

    server = DNSServer(config)

    assert server._get_record_type_name(DNSRecordType.A) == "A"
    assert server._get_record_type_name(DNSRecordType.AAAA) == "AAAA"
    assert server._get_record_type_name(DNSRecordType.CNAME) == "CNAME"
    assert server._get_record_type_name(999) == "TYPE999"


def test_response_code_names():
    """Test DNS response code name mapping"""
    config = Mock()
    config.upstream_servers = []

    server = DNSServer(config)

    assert server._get_response_code_name(DNSResponseCode.NOERROR) == "NOERROR"
    assert server._get_response_code_name(DNSResponseCode.NXDOMAIN) == "NXDOMAIN"
    assert server._get_response_code_name(DNSResponseCode.SERVFAIL) == "SERVFAIL"
    assert server._get_response_code_name(999) == "RCODE999"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
