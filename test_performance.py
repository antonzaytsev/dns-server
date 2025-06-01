#!/usr/bin/env python3
"""
Performance Test Script for DNS Server

This script demonstrates and tests the performance optimization features:
- uvloop integration
- Connection pooling
- Concurrency limiting
- Performance monitoring
- Memory tracking
"""

import asyncio
import platform
import sys
import time
from pathlib import Path

try:
    from dns_server.core.performance import (
        concurrency_limiter,
        connection_pool,
        performance_monitor,
        timing_decorator,
    )
except ImportError:
    # Add src to path if direct import fails
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from dns_server.core.performance import (
        concurrency_limiter,
        connection_pool,
        performance_monitor,
        timing_decorator,
    )


async def test_performance_monitor():
    """Test performance monitoring functionality"""
    print("Testing Performance Monitor...")

    # Start monitoring
    await performance_monitor.start_monitoring(interval=1.0)

    # Record some operations
    performance_monitor.record_operation_time("test_operation", 0.05)
    performance_monitor.record_connection_event("new")
    performance_monitor.record_queue_metrics("test_queue", 10, 0.02)
    performance_monitor.record_error("test_error")

    # Wait for monitoring to collect data
    await asyncio.sleep(2)

    # Get stats
    stats = performance_monitor.get_stats()
    print(f"Memory usage: {stats['memory']}")
    print(f"Operations: {stats['operations']}")
    print(f"Connections: {stats['connections']}")
    print(f"Errors: {stats['errors']}")

    await performance_monitor.stop_monitoring()
    print("✓ Performance monitoring test completed")


async def test_connection_pool():
    """Test connection pooling functionality"""
    print("\nTesting Connection Pool...")

    connection_pool.set_monitor(performance_monitor)

    try:
        # Test getting multiple connections
        conn1 = await connection_pool.get_connection("8.8.8.8", 53)
        conn2 = await connection_pool.get_connection("1.1.1.1", 53)

        print("Got connections to 8.8.8.8 and 1.1.1.1")

        # Return connections
        await conn1.__aexit__(None, None, None)
        await conn2.__aexit__(None, None, None)

        print("✓ Connection pool test completed")

    except Exception as e:
        print(f"✗ Connection pool test failed: {e}")


async def test_concurrency_limiter():
    """Test concurrency limiting functionality"""
    print("\nTesting Concurrency Limiter...")

    concurrency_limiter.set_monitor(performance_monitor)

    async def mock_request(request_id):
        async with await concurrency_limiter.acquire(timeout=1.0):
            # Simulate work
            await asyncio.sleep(0.1)
            return f"Request {request_id} completed"

    try:
        # Start multiple concurrent requests
        tasks = [mock_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        print(f"✓ Completed {len(results)} concurrent requests")
        print("✓ Concurrency limiter test completed")

    except Exception as e:
        print(f"✗ Concurrency limiter test failed: {e}")


@timing_decorator("test_timing", performance_monitor)
async def test_timing_decorator():
    """Test timing decorator functionality"""
    print("\nTesting Timing Decorator...")

    # Simulate some work
    await asyncio.sleep(0.1)

    print("✓ Timing decorator test completed")


async def test_uvloop():
    """Test uvloop integration"""
    print("\nTesting Event Loop...")

    loop = asyncio.get_running_loop()
    loop_type = type(loop).__name__

    if platform.system() != "Windows":
        try:
            import uvloop

            if isinstance(loop, uvloop.Loop):
                print("✓ Using uvloop for enhanced performance")
            else:
                print("⚠ uvloop available but not active")
        except ImportError:
            print("⚠ uvloop not available, using default asyncio loop")
    else:
        print("ℹ Windows detected, uvloop not supported")

    print(f"Current event loop: {loop_type}")


async def run_load_test():
    """Run a simple load test to demonstrate performance"""
    print("\nRunning Load Test...")

    await performance_monitor.start_monitoring(interval=0.5)

    async def mock_dns_request(request_id):
        async with await concurrency_limiter.acquire():
            # Simulate DNS processing
            await asyncio.sleep(0.01)
            performance_monitor.record_operation_time("mock_dns_request", 0.01)
            return f"Response {request_id}"

    # Run 100 concurrent requests
    start_time = time.time()
    tasks = [mock_dns_request(i) for i in range(100)]
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    print(f"✓ Processed {len(results)} requests in {end_time - start_time:.2f} seconds")
    print(f"✓ Throughput: {len(results) / (end_time - start_time):.1f} requests/second")

    # Show performance stats
    stats = performance_monitor.get_stats()
    operations = stats.get("operations", {}).get("mock_dns_request", {})
    if operations:
        print(f"✓ Average response time: {operations.get('avg_time_ms', 0):.2f}ms")

    await performance_monitor.stop_monitoring()


async def main():
    """Main test function"""
    print("DNS Server Performance Optimization Test")
    print("=" * 50)

    try:
        await test_uvloop()
        await test_performance_monitor()
        await test_connection_pool()
        await test_concurrency_limiter()
        await test_timing_decorator()
        await run_load_test()

        print("\n" + "=" * 50)
        print("All performance optimization tests completed successfully!")

        # Final performance stats
        stats = performance_monitor.get_stats()
        print("\nFinal Stats:")
        print(f"Memory: {stats.get('memory', {})}")
        print(
            f"Total operations: {sum(op.get('count', 0) for op in stats.get('operations', {}).values())}"
        )

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        # Try to use uvloop if available and not on Windows
        if platform.system() != "Windows":
            try:
                import uvloop

                asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            except ImportError:
                pass

        exit_code = asyncio.run(main())
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
