"""
DNS Cache Engine - Phase 3 Implementation

High-performance DNS response caching with LRU eviction, TTL awareness,
memory management, and comprehensive statistics.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional

from ..core.message import DNSMessage, DNSQuestion, DNSResponseCode
from .entry import (
    CacheEntry,
    CacheEntryType,
    create_negative_cache_entry,
    generate_cache_key,
)
from .stats import CacheStatsManager


class DNSCache:
    """Advanced DNS cache implementation for Phase 3"""

    def __init__(
        self,
        max_size: int = 10000,
        max_memory_mb: int = 100,
        default_ttl: int = 300,
        min_ttl: int = 1,
        max_ttl: int = 86400,
        negative_ttl: int = 300,
        cleanup_interval: int = 60,
    ):
        """
        Initialize DNS cache with configuration

        Args:
            max_size: Maximum number of cache entries
            max_memory_mb: Maximum memory usage in MB
            default_ttl: Default TTL when none specified
            min_ttl: Minimum TTL value
            max_ttl: Maximum TTL value
            negative_ttl: TTL for negative cache entries
            cleanup_interval: Cleanup interval in seconds
        """
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self.min_ttl = min_ttl
        self.max_ttl = max_ttl
        self.negative_ttl = negative_ttl

        # LRU cache using OrderedDict
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # Statistics manager
        self.stats = CacheStatsManager(max_memory_mb)

        # Current memory usage tracking
        self._current_memory = 0

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = cleanup_interval

        # Logger
        self.logger = logging.getLogger(__name__)

        # Start cleanup task
        self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of expired entries"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cache cleanup: {e}")

    async def _cleanup_expired(self) -> int:
        """Remove expired entries from cache"""
        expired_keys = []

        async with self._lock:
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)

        # Remove expired entries
        for key in expired_keys:
            await self._remove_entry(key, "ttl")

        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    async def _remove_entry(self, key: str, eviction_type: str = "lru") -> None:
        """Remove entry from cache and update statistics"""
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                self._current_memory -= entry.memory_size
                del self._cache[key]
                await self.stats.record_eviction(eviction_type)
                await self.stats.update_cache_size(
                    len(self._cache), self._current_memory
                )

    async def _evict_lru(self) -> None:
        """Evict least recently used entry"""
        if self._cache:
            # OrderedDict maintains insertion order, move_to_end() for LRU
            oldest_key = next(iter(self._cache))
            await self._remove_entry(oldest_key, "lru")

    async def _enforce_memory_limit(self) -> None:
        """Enforce memory limits by evicting entries"""
        while self._current_memory > self.max_memory_bytes and self._cache:
            # Find largest entry to evict first for memory efficiency
            largest_key = max(
                self._cache.keys(), key=lambda k: self._cache[k].memory_size
            )
            await self._remove_entry(largest_key, "memory")

    async def _enforce_size_limit(self) -> None:
        """Enforce entry count limits by evicting LRU entries"""
        while len(self._cache) >= self.max_size:
            await self._evict_lru()

    def _calculate_ttl(self, response: DNSMessage) -> int:
        """Calculate TTL from DNS response"""
        if not response.answers:
            return self.default_ttl

        # Use minimum TTL from all answer records
        ttl = min(answer.ttl for answer in response.answers)

        # Enforce TTL limits
        ttl = max(self.min_ttl, min(self.max_ttl, ttl))

        return ttl

    async def get(self, question: DNSQuestion) -> Optional[DNSMessage]:
        """Get cached response for question"""
        start_time = time.time()

        await self.stats.record_request()

        async with self._lock:
            key = generate_cache_key(question)
            entry = self._cache.get(key)

            if entry is None:
                lookup_time_ms = (time.time() - start_time) * 1000
                await self.stats.record_miss(lookup_time_ms)
                return None

            if entry.is_expired():
                # Remove expired entry
                self._current_memory -= entry.memory_size
                del self._cache[key]
                await self.stats.record_eviction("ttl")
                await self.stats.update_cache_size(
                    len(self._cache), self._current_memory
                )

                lookup_time_ms = (time.time() - start_time) * 1000
                await self.stats.record_miss(lookup_time_ms)
                return None

            # Move to end for LRU (most recently used)
            self._cache.move_to_end(key)
            entry.access()

            lookup_time_ms = (time.time() - start_time) * 1000
            is_negative = entry.entry_type == CacheEntryType.NEGATIVE
            await self.stats.record_hit(lookup_time_ms, is_negative)

            return entry.response

    async def put(self, question: DNSQuestion, response: DNSMessage) -> None:
        """Cache response for question"""
        key = generate_cache_key(question)

        # Determine if this is a negative response
        # Note: Using hasattr to check for response_code attribute
        is_negative = (
            hasattr(response.header, "rcode")
            and response.header.rcode == DNSResponseCode.NXDOMAIN
        ) or (
            hasattr(response.header, "rcode")
            and response.header.rcode == DNSResponseCode.NOERROR
            and not response.answers
        )

        if is_negative:
            entry = create_negative_cache_entry(question, response, self.negative_ttl)
        else:
            ttl = self._calculate_ttl(response)
            entry = CacheEntry(
                response=response,
                created_at=time.time(),
                ttl=ttl,
                entry_type=CacheEntryType.POSITIVE,
                original_ttl=ttl,
            )

        async with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                old_entry = self._cache[key]
                self._current_memory -= old_entry.memory_size
                del self._cache[key]

            # Enforce limits before adding new entry
            await self._enforce_size_limit()

            # Add new entry
            self._cache[key] = entry
            self._current_memory += entry.memory_size

            # Enforce memory limit after adding
            await self._enforce_memory_limit()

            # Update statistics
            await self.stats.update_cache_size(len(self._cache), self._current_memory)

    async def invalidate(self, domain: str, qtype: Optional[int] = None) -> int:
        """Invalidate cache entries for domain and optionally query type"""
        invalidated = 0
        keys_to_remove = []

        async with self._lock:
            for key in self._cache.keys():
                parts = key.split(":")
                cached_domain = parts[0]
                cached_qtype = int(parts[1]) if len(parts) > 1 else None

                if cached_domain == domain.lower():
                    if qtype is None or cached_qtype == qtype:
                        keys_to_remove.append(key)

        for key in keys_to_remove:
            await self._remove_entry(key, "manual")
            invalidated += 1

        self.logger.info(f"Invalidated {invalidated} cache entries for domain {domain}")
        return invalidated

    async def flush(self) -> int:
        """Flush entire cache"""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._current_memory = 0
            await self.stats.update_cache_size(0, 0)

        self.logger.info(f"Flushed {count} cache entries")
        return count

    async def get_entries_to_refresh(self, threshold: float = 0.1) -> List[str]:
        """Get cache keys that should be proactively refreshed"""
        refresh_keys = []

        async with self._lock:
            for key, entry in self._cache.items():
                if entry.should_refresh(threshold):
                    refresh_keys.append(key)

        return refresh_keys

    async def warm_cache(self, entries: List[tuple]) -> int:
        """Warm cache with pre-computed entries"""
        warmed = 0

        for question, response in entries:
            await self.put(question, response)
            warmed += 1

        self.logger.info(f"Warmed cache with {warmed} entries")
        return warmed

    async def get_cache_info(self) -> Dict:
        """Get comprehensive cache information"""
        stats = await self.stats.get_stats()

        async with self._lock:
            # Add cache-specific information
            stats.update(
                {
                    "max_size": self.max_size,
                    "max_memory_mb": self.max_memory_bytes // (1024 * 1024),
                    "default_ttl": self.default_ttl,
                    "min_ttl": self.min_ttl,
                    "max_ttl": self.max_ttl,
                    "negative_ttl": self.negative_ttl,
                    "cleanup_interval": self._cleanup_interval,
                }
            )

        return stats

    async def shutdown(self) -> None:
        """Shutdown cache and cleanup resources"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.flush()
        self.logger.info("DNS cache shutdown complete")
