"""
DNS Cache Entry Management

Comprehensive cache entry implementation for Phase 3.
"""

import time
from dataclasses import dataclass, field
from enum import Enum

from ..core.message import DNSMessage, DNSQuestion


class CacheEntryType(Enum):
    """Type of cache entry"""

    POSITIVE = "positive"  # Normal DNS response
    NEGATIVE = "negative"  # NXDOMAIN or NODATA response


@dataclass
class CacheEntry:
    """Enhanced cache entry with full Phase 3 features"""

    response: DNSMessage
    created_at: float
    ttl: int
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    entry_type: CacheEntryType = CacheEntryType.POSITIVE
    original_ttl: int = 0  # Original TTL for statistics
    memory_size: int = 0  # Estimated memory usage in bytes

    def __post_init__(self) -> None:
        """Initialize computed fields"""
        if self.original_ttl == 0:
            self.original_ttl = self.ttl
        if self.memory_size == 0:
            self.memory_size = self._estimate_memory_size()

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return time.time() > (self.created_at + self.ttl)

    def remaining_ttl(self) -> int:
        """Get remaining TTL in seconds"""
        remaining = int(self.ttl - (time.time() - self.created_at))
        return max(0, remaining)

    def access(self) -> None:
        """Record an access to this cache entry"""
        self.access_count += 1
        self.last_accessed = time.time()

    def should_refresh(self, refresh_threshold: float = 0.1) -> bool:
        """Check if entry should be proactively refreshed"""
        remaining_ratio = self.remaining_ttl() / self.original_ttl
        return remaining_ratio <= refresh_threshold

    def _estimate_memory_size(self) -> int:
        """Estimate memory usage of this cache entry in bytes"""
        # Basic estimation: message size + metadata overhead
        base_size = 200  # Estimated overhead for CacheEntry fields

        # Estimate DNS message size
        message_size = 0
        if self.response:
            # Header: 12 bytes
            message_size += 12

            # Questions
            for question in self.response.questions:
                message_size += len(question.name.encode()) + 4  # name + type + class

            # Answers, Authority, Additional
            for section in [
                self.response.answers,
                self.response.authority,
                self.response.additional,
            ]:
                for record in section:
                    message_size += len(str(record).encode())

        return base_size + message_size


def generate_cache_key(question: DNSQuestion) -> str:
    """Generate standardized cache key from DNS question"""
    return f"{question.name.lower()}:{question.qtype}:{question.qclass}"


def create_negative_cache_entry(
    question: DNSQuestion, response: DNSMessage, negative_ttl: int
) -> CacheEntry:
    """Create a cache entry for negative responses (NXDOMAIN, NODATA)"""
    return CacheEntry(
        response=response,
        created_at=time.time(),
        ttl=negative_ttl,
        entry_type=CacheEntryType.NEGATIVE,
        original_ttl=negative_ttl,
    )
