"""
DNS Cache Engine - Basic Implementation for Phase 2

This is a simplified cache implementation to support Phase 2.
The full cache system will be implemented in Phase 3.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

from ..core.message import DNSMessage, DNSQuestion


@dataclass
class CacheEntry:
    """Basic cache entry"""

    response: DNSMessage
    created_at: float
    ttl: int

    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl)


class BasicDNSCache:
    """Basic DNS cache for Phase 2"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _generate_key(self, question: DNSQuestion) -> str:
        """Generate cache key from DNS question"""
        return f"{question.name}:{question.qtype}:{question.qclass}"

    async def get(self, question: DNSQuestion) -> Optional[DNSMessage]:
        """Get cached response for question"""
        async with self._lock:
            key = self._generate_key(question)
            entry = self._cache.get(key)

            if entry and not entry.is_expired():
                return entry.response
            elif entry:
                # Remove expired entry
                del self._cache[key]

            return None

    async def put(self, question: DNSQuestion, response: DNSMessage):
        """Cache response for question"""
        async with self._lock:
            # Extract TTL from response
            ttl = 300  # Default 5 minutes
            if response.answers:
                ttl = min(answer.ttl for answer in response.answers)

            key = self._generate_key(question)

            # Evict old entries if cache is full
            if len(self._cache) >= self.max_size and key not in self._cache:
                # Simple LRU: remove oldest entry
                oldest_key = min(
                    self._cache.keys(), key=lambda k: self._cache[k].created_at
                )
                del self._cache[oldest_key]

            self._cache[key] = CacheEntry(
                response=response, created_at=time.time(), ttl=ttl
            )

    async def get_stats(self) -> Dict:
        """Get basic cache statistics"""
        async with self._lock:
            return {
                "entries": len(self._cache),
                "max_size": self.max_size,
                "status": "available",
            }
