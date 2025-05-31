"""
DNS Cache Statistics

Comprehensive statistics tracking for Phase 3 cache implementation.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CacheStats:
    """Cache statistics data structure"""

    # Hit/Miss Statistics
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    negative_hits: int = 0  # Hits on negative cache entries

    # Cache Size Statistics
    current_entries: int = 0
    max_entries_reached: int = 0

    # Memory Statistics
    current_memory_bytes: int = 0
    max_memory_bytes: int = 0
    memory_limit_bytes: int = 0

    # Performance Statistics
    average_lookup_time_ms: float = 0.0
    total_lookup_time_ms: float = 0.0
    lookup_times: deque = field(default_factory=lambda: deque(maxlen=1000))

    # Eviction Statistics
    total_evictions: int = 0
    lru_evictions: int = 0
    ttl_expirations: int = 0
    memory_evictions: int = 0

    # Time-based Statistics
    start_time: float = field(default_factory=time.time)
    last_reset: float = field(default_factory=time.time)

    def hit_ratio(self) -> float:
        """Calculate cache hit ratio"""
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests

    def miss_ratio(self) -> float:
        """Calculate cache miss ratio"""
        if self.total_requests == 0:
            return 0.0
        return self.cache_misses / self.total_requests

    def memory_usage_ratio(self) -> float:
        """Calculate memory usage ratio"""
        if self.memory_limit_bytes == 0:
            return 0.0
        return self.current_memory_bytes / self.memory_limit_bytes

    def uptime_seconds(self) -> float:
        """Get cache uptime in seconds"""
        return time.time() - self.start_time

    def requests_per_second(self) -> float:
        """Calculate requests per second"""
        uptime = self.uptime_seconds()
        if uptime == 0:
            return 0.0
        return self.total_requests / uptime


class CacheStatsManager:
    """Manager for cache statistics tracking"""

    def __init__(self, memory_limit_mb: int = 100):
        self.stats = CacheStats(memory_limit_bytes=memory_limit_mb * 1024 * 1024)
        self._lock = asyncio.Lock()

    async def record_request(self) -> None:
        """Record a cache request"""
        async with self._lock:
            self.stats.total_requests += 1

    async def record_hit(
        self, lookup_time_ms: float, is_negative: bool = False
    ) -> None:
        """Record a cache hit"""
        async with self._lock:
            self.stats.cache_hits += 1
            if is_negative:
                self.stats.negative_hits += 1
            self._record_lookup_time(lookup_time_ms)

    async def record_miss(self, lookup_time_ms: float) -> None:
        """Record a cache miss"""
        async with self._lock:
            self.stats.cache_misses += 1
            self._record_lookup_time(lookup_time_ms)

    def _record_lookup_time(self, lookup_time_ms: float) -> None:
        """Record lookup time and update average"""
        self.stats.lookup_times.append(lookup_time_ms)
        self.stats.total_lookup_time_ms += lookup_time_ms

        # Update average (using recent samples for efficiency)
        if len(self.stats.lookup_times) > 0:
            self.stats.average_lookup_time_ms = sum(self.stats.lookup_times) / len(
                self.stats.lookup_times
            )

    async def update_cache_size(self, entries: int, memory_bytes: int) -> None:
        """Update cache size statistics"""
        async with self._lock:
            self.stats.current_entries = entries
            self.stats.current_memory_bytes = memory_bytes

            # Track maximums
            if entries > self.stats.max_entries_reached:
                self.stats.max_entries_reached = entries

            if memory_bytes > self.stats.max_memory_bytes:
                self.stats.max_memory_bytes = memory_bytes

    async def record_eviction(self, eviction_type: str) -> None:
        """Record cache eviction"""
        async with self._lock:
            self.stats.total_evictions += 1

            if eviction_type == "lru":
                self.stats.lru_evictions += 1
            elif eviction_type == "ttl":
                self.stats.ttl_expirations += 1
            elif eviction_type == "memory":
                self.stats.memory_evictions += 1

    async def get_stats(self) -> Dict:
        """Get comprehensive cache statistics"""
        async with self._lock:
            uptime = self.stats.uptime_seconds()

            return {
                # Hit/Miss Statistics
                "hit_ratio": round(self.stats.hit_ratio(), 4),
                "miss_ratio": round(self.stats.miss_ratio(), 4),
                "total_requests": self.stats.total_requests,
                "cache_hits": self.stats.cache_hits,
                "cache_misses": self.stats.cache_misses,
                "negative_hits": self.stats.negative_hits,
                # Performance Statistics
                "average_lookup_time_ms": round(self.stats.average_lookup_time_ms, 2),
                "requests_per_second": round(self.stats.requests_per_second(), 2),
                # Cache Size Statistics
                "current_entries": self.stats.current_entries,
                "max_entries_reached": self.stats.max_entries_reached,
                # Memory Statistics
                "current_memory_mb": round(
                    self.stats.current_memory_bytes / (1024 * 1024), 2
                ),
                "max_memory_mb": round(self.stats.max_memory_bytes / (1024 * 1024), 2),
                "memory_limit_mb": round(
                    self.stats.memory_limit_bytes / (1024 * 1024), 2
                ),
                "memory_usage_ratio": round(self.stats.memory_usage_ratio(), 4),
                # Eviction Statistics
                "total_evictions": self.stats.total_evictions,
                "lru_evictions": self.stats.lru_evictions,
                "ttl_expirations": self.stats.ttl_expirations,
                "memory_evictions": self.stats.memory_evictions,
                # Time Statistics
                "uptime_seconds": round(uptime, 2),
                "start_time": self.stats.start_time,
                "last_reset": self.stats.last_reset,
            }

    async def reset_stats(self) -> None:
        """Reset all statistics"""
        async with self._lock:
            self.stats = CacheStats(memory_limit_bytes=self.stats.memory_limit_bytes)
            self.stats.last_reset = time.time()

    async def get_performance_history(self) -> List[float]:
        """Get recent lookup time history"""
        async with self._lock:
            return list(self.stats.lookup_times)
