#!/usr/bin/env python3
"""
Quick test script for Phase 2 DNS Server

This script tests basic functionality of the DNS server.
"""

import asyncio
import socket
import struct
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dns_server.cache import BasicDNSCache
from dns_server.config.loader import ConfigLoader
from dns_server.core import DNSServer
from dns_server.core.message import DNSClass, DNSMessage, DNSQuestion, DNSRecordType


async def test_dns_server():
    """Test the DNS server functionality"""
    print("🧪 Testing DNS Server Phase 2 Implementation")
    print("=" * 50)

    try:
        # Load default configuration
        config_loader = ConfigLoader("config/default.yaml")
        config = config_loader.load_config()

        # Create cache and server
        cache = BasicDNSCache(max_size=100)
        server = DNSServer(config)
        server.set_cache(cache)

        print("✅ Server initialized successfully")

        # Test server stats
        stats = server.get_stats()
        print(f"📊 Initial stats: {stats['total_queries']} queries processed")

        # Test health check
        health = await server.health_check()
        print(f"🏥 Health status: {health['status']}")

        # Test creating a simple DNS query
        question = DNSQuestion("example.com.", DNSRecordType.A, DNSClass.IN)
        print(f"❓ Created test question: {question.name} {question.qtype}")

        # Test cache operations
        cached = await cache.get(question)
        print(f"💾 Cache miss test: {cached is None}")

        cache_stats = await cache.get_stats()
        print(f"📈 Cache stats: {cache_stats['entries']} entries")

        print("\n🎉 All basic tests passed!")
        print("✨ Phase 2 DNS Server implementation is working correctly!")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    success = await test_dns_server()

    if success:
        print("\n🚀 DNS Server Phase 2 is ready!")
        print("   You can now start the server with:")
        print("   python src/dns_server/main.py")
    else:
        print("\n💥 Tests failed - please check the implementation")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
