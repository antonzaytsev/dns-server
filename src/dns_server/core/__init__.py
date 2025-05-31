"""
DNS Server Core Module

This module exports the main DNS server components for Phase 2.
"""

from .message import (
    DNSClass,
    DNSHeader,
    DNSMessage,
    DNSOpcode,
    DNSQuestion,
    DNSRecordType,
    DNSResourceRecord,
    DNSResponseCode,
    create_a_record,
    create_aaaa_record,
    create_cname_record,
    create_mx_record,
    create_txt_record,
)
from .resolver import DNSResolver, IterativeResolver
from .server import DNSServer

__all__ = [
    # Main server
    "DNSServer",
    # Resolvers
    "DNSResolver",
    "IterativeResolver",
    # Message components
    "DNSMessage",
    "DNSQuestion",
    "DNSResourceRecord",
    "DNSHeader",
    # Enums
    "DNSRecordType",
    "DNSClass",
    "DNSResponseCode",
    "DNSOpcode",
    # Helper functions
    "create_a_record",
    "create_aaaa_record",
    "create_cname_record",
    "create_mx_record",
    "create_txt_record",
]
