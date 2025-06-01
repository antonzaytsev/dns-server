"""
Performance Monitoring and Optimization Module

This module provides:
- Timing decorators for all operations
- Performance metrics collection
- Memory usage tracking
- Connection pooling management
- Concurrency limiting
"""

import asyncio
import functools
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""

    # Timing metrics
    operation_times: Dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    operation_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Memory metrics
    memory_usage: deque = field(default_factory=lambda: deque(maxlen=100))
    memory_peak: float = 0.0

    # Connection metrics
    active_connections: int = 0
    total_connections: int = 0
    rejected_connections: int = 0

    # Queue metrics
    queue_sizes: Dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=100))
    )
    queue_wait_times: Dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )

    # Error metrics
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_rates: Dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=100))
    )


class PerformanceMonitor:
    """Performance monitoring and metrics collection"""

    def __init__(self):
        self.metrics = PerformanceMetrics()
        self._start_time = time.time()
        self._monitoring_task = None
        self._is_monitoring = False

    async def start_monitoring(self, interval: float = 5.0):
        """Start background monitoring"""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop(interval))
        logger.info("Performance monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring"""
        if not self._is_monitoring:
            return

        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitoring stopped")

    async def _monitor_loop(self, interval: float):
        """Background monitoring loop"""
        while self._is_monitoring:
            try:
                # Collect memory metrics
                process = psutil.Process()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024

                self.metrics.memory_usage.append(memory_mb)
                if memory_mb > self.metrics.memory_peak:
                    self.metrics.memory_peak = memory_mb

                # Log warnings for high memory usage
                if memory_mb > 1000:  # > 1GB
                    logger.warning(f"High memory usage: {memory_mb:.1f} MB")

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)

    def record_operation_time(self, operation: str, duration: float):
        """Record timing for an operation"""
        self.metrics.operation_times[operation].append(duration)
        self.metrics.operation_counts[operation] += 1

    def record_connection_event(self, event_type: str):
        """Record connection events"""
        if event_type == "new":
            self.metrics.active_connections += 1
            self.metrics.total_connections += 1
        elif event_type == "closed":
            self.metrics.active_connections = max(
                0, self.metrics.active_connections - 1
            )
        elif event_type == "rejected":
            self.metrics.rejected_connections += 1

    def record_queue_metrics(self, queue_name: str, size: int, wait_time: float = None):
        """Record queue metrics"""
        self.metrics.queue_sizes[queue_name].append(size)
        if wait_time is not None:
            self.metrics.queue_wait_times[queue_name].append(wait_time)

    def record_error(self, error_type: str):
        """Record error occurrence"""
        self.metrics.error_counts[error_type] += 1
        current_time = time.time()
        self.metrics.error_rates[error_type].append(current_time)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        stats = {
            "uptime_seconds": time.time() - self._start_time,
            "memory": self._get_memory_stats(),
            "operations": self._get_operation_stats(),
            "connections": self._get_connection_stats(),
            "queues": self._get_queue_stats(),
            "errors": self._get_error_stats(),
        }
        return stats

    def _get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        if not self.metrics.memory_usage:
            return {"current_mb": 0, "peak_mb": 0, "average_mb": 0}

        current = self.metrics.memory_usage[-1]
        average = sum(self.metrics.memory_usage) / len(self.metrics.memory_usage)

        return {
            "current_mb": round(current, 2),
            "peak_mb": round(self.metrics.memory_peak, 2),
            "average_mb": round(average, 2),
        }

    def _get_operation_stats(self) -> Dict[str, Any]:
        """Get operation timing statistics"""
        stats = {}
        for operation, times in self.metrics.operation_times.items():
            if times:
                avg_time = sum(times) / len(times)
                min_time = min(times)
                max_time = max(times)
                count = self.metrics.operation_counts[operation]

                stats[operation] = {
                    "count": count,
                    "avg_time_ms": round(avg_time * 1000, 2),
                    "min_time_ms": round(min_time * 1000, 2),
                    "max_time_ms": round(max_time * 1000, 2),
                }
        return stats

    def _get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "active": self.metrics.active_connections,
            "total": self.metrics.total_connections,
            "rejected": self.metrics.rejected_connections,
        }

    def _get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        stats = {}
        for queue_name, sizes in self.metrics.queue_sizes.items():
            if sizes:
                avg_size = sum(sizes) / len(sizes)
                max_size = max(sizes)
                current_size = sizes[-1]

                wait_times = self.metrics.queue_wait_times[queue_name]
                avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0

                stats[queue_name] = {
                    "current_size": current_size,
                    "avg_size": round(avg_size, 2),
                    "max_size": max_size,
                    "avg_wait_time_ms": round(avg_wait * 1000, 2),
                }
        return stats

    def _get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        stats = {}
        current_time = time.time()

        for error_type, count in self.metrics.error_counts.items():
            # Calculate error rate (errors per minute in last 5 minutes)
            recent_errors = [
                t
                for t in self.metrics.error_rates[error_type]
                if current_time - t < 300  # 5 minutes
            ]
            error_rate = len(recent_errors) / 5.0  # per minute

            stats[error_type] = {
                "total_count": count,
                "rate_per_minute": round(error_rate, 2),
            }
        return stats


def timing_decorator(operation_name: str, monitor: PerformanceMonitor):
    """Decorator to time function execution"""

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception:
                    if monitor:
                        monitor.record_error(f"{operation_name}_error")
                    raise
                finally:
                    duration = time.time() - start_time
                    if monitor:
                        monitor.record_operation_time(operation_name, duration)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception:
                    if monitor:
                        monitor.record_error(f"{operation_name}_error")
                    raise
                finally:
                    duration = time.time() - start_time
                    if monitor:
                        monitor.record_operation_time(operation_name, duration)

            return sync_wrapper

    return decorator


class ConnectionPool:
    """Connection pool for upstream DNS queries"""

    def __init__(self, max_connections: int = 100, connection_timeout: float = 30.0):
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self._pools = {}  # server -> list of connections
        self._in_use = {}  # server -> set of connection ids
        self._lock = asyncio.Lock()
        self._monitor = None
        self._connection_counter = 0

    def set_monitor(self, monitor: PerformanceMonitor):
        """Set performance monitor"""
        self._monitor = monitor

    async def get_connection(self, server: str, port: int):
        """Get a connection from the pool"""
        server_key = f"{server}:{port}"

        async with self._lock:
            # Initialize server pools if needed
            if server_key not in self._pools:
                self._pools[server_key] = []
                self._in_use[server_key] = set()

            # Try to reuse existing connection
            available_connections = [
                conn
                for conn in self._pools[server_key]
                if conn["id"] not in self._in_use[server_key]
            ]

            if available_connections:
                connection = available_connections[0]
                self._in_use[server_key].add(connection["id"])
                return ConnectionWrapper(connection, self, server_key)

            # Create new connection if under limit
            total_connections = sum(len(pool) for pool in self._pools.values())
            if total_connections < self.max_connections:
                connection = await self._create_connection(server, port)
                self._pools[server_key].append(connection)
                self._in_use[server_key].add(connection["id"])

                if self._monitor:
                    self._monitor.record_connection_event("new")

                return ConnectionWrapper(connection, self, server_key)

            # Pool exhausted
            if self._monitor:
                self._monitor.record_connection_event("rejected")
            raise RuntimeError("Connection pool exhausted")

    async def _create_connection(self, server: str, port: int):
        """Create a new connection"""
        # For DNS, we use UDP sockets which are connectionless
        # But we can still pool them for reuse
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)  # Essential for asyncio operations

        # Set socket options for better performance
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Set receive buffer size
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        except OSError:
            pass  # Ignore if not supported

        self._connection_counter += 1

        logger.debug(
            f"Created new UDP socket connection {self._connection_counter} for {server}:{port}"
        )

        return {
            "id": self._connection_counter,
            "socket": sock,
            "server": server,
            "port": port,
            "created": time.time(),
        }

    async def return_connection(self, connection, server_key: str):
        """Return a connection to the pool"""
        async with self._lock:
            if server_key in self._in_use:
                self._in_use[server_key].discard(connection["id"])

    async def cleanup_old_connections(self):
        """Clean up old connections"""
        current_time = time.time()
        async with self._lock:
            for server_key, pool in list(self._pools.items()):
                new_pool = []
                old_connections = []

                for conn in pool:
                    if current_time - conn["created"] < self.connection_timeout:
                        new_pool.append(conn)
                    else:
                        old_connections.append(conn)

                self._pools[server_key] = new_pool

                # Close old connections
                for conn in old_connections:
                    try:
                        conn["socket"].close()
                        if self._monitor:
                            self._monitor.record_connection_event("closed")
                    except Exception:
                        pass


class ConnectionWrapper:
    """Wrapper for pooled connections"""

    def __init__(self, connection, pool: ConnectionPool, server_key: str):
        self.connection = connection
        self._pool = pool
        self._server_key = server_key
        self._returned = False

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._returned:
            await self._pool.return_connection(self.connection, self._server_key)
            self._returned = True


class ConcurrencyLimiter:
    """Limits concurrent operations with queuing and backpressure"""

    def __init__(self, max_concurrent: int = 1000, queue_size: int = 5000):
        self.max_concurrent = max_concurrent
        self.queue_size = queue_size
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue = asyncio.Queue(maxsize=queue_size)
        self._active_count = 0
        self._monitor = None

    def set_monitor(self, monitor: PerformanceMonitor):
        """Set performance monitor"""
        self._monitor = monitor

    async def acquire(self, timeout: float = 30.0):
        """Acquire permission to proceed"""
        start_time = time.time()

        try:
            # Check if we can proceed immediately
            try:
                self._semaphore.acquire_nowait()
                acquired = True
            except Exception:
                acquired = False

            if acquired:
                self._active_count += 1
                if self._monitor:
                    self._monitor.record_queue_metrics(
                        "concurrency", self._active_count, 0
                    )
                return ConcurrencyContext(self)

            # Need to wait - check queue capacity
            if self._queue.qsize() >= self.queue_size:
                if self._monitor:
                    self._monitor.record_error("queue_full")
                raise RuntimeError("Request queue full - backpressure applied")

            # Wait for permission
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            wait_time = time.time() - start_time
            self._active_count += 1

            if self._monitor:
                self._monitor.record_queue_metrics(
                    "concurrency", self._active_count, wait_time
                )

            return ConcurrencyContext(self)

        except asyncio.TimeoutError:
            if self._monitor:
                self._monitor.record_error("concurrency_timeout")
            raise RuntimeError("Concurrency limit timeout")

    def release(self):
        """Release concurrent operation slot"""
        self._semaphore.release()
        self._active_count = max(0, self._active_count - 1)

        if self._monitor:
            self._monitor.record_queue_metrics("concurrency", self._active_count)


class ConcurrencyContext:
    """Context manager for concurrency limiting"""

    def __init__(self, limiter: ConcurrencyLimiter):
        self._limiter = limiter

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._limiter.release()


# Global instances
performance_monitor = PerformanceMonitor()
connection_pool = ConnectionPool()
concurrency_limiter = ConcurrencyLimiter()

# Set up cross-references
connection_pool.set_monitor(performance_monitor)
concurrency_limiter.set_monitor(performance_monitor)
