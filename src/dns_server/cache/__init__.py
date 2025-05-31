"""
DNS Cache Module - Phase 3 Implementation

Advanced caching system with LRU eviction, TTL awareness, memory management,
comprehensive statistics, and cache management API.
"""

from .engine import DNSCache
from .entry import (
    CacheEntry,
    CacheEntryType,
    create_negative_cache_entry,
    generate_cache_key,
)
from .manager import CacheManager
from .stats import CacheStats, CacheStatsManager

# Backward compatibility - alias for Phase 2 components that might still be used
BasicDNSCache = DNSCache  # For any code still referencing the old name

__all__ = [
    # Phase 3 Cache Engine
    "DNSCache",
    # Cache Entry Management
    "CacheEntry",
    "CacheEntryType",
    "generate_cache_key",
    "create_negative_cache_entry",
    # Statistics
    "CacheStats",
    "CacheStatsManager",
    # Cache Management
    "CacheManager",
    # Backward Compatibility
    "BasicDNSCache",
]
