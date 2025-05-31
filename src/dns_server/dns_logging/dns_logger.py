"""
DNS Request/Response Logging

This module provides DNS-specific logging functionality with the exact JSON format
specified in the requirements, including request ID tracking and performance timing.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dns import message, rcode

from .logger import get_logger


class DNSRequestLogger:
    """DNS request/response logger with structured JSON output."""

    def __init__(self):
        """Initialize DNS logger."""
        self.logger = get_logger("dns_requests")

    def log_dns_request(
        self,
        request_id: str,
        client_ip: str,
        query_type: str,
        domain: str,
        response_code: str,
        response_time_ms: float,
        cache_hit: bool,
        upstream_server: Optional[str] = None,
        response_data: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log DNS request/response in the specified JSON format.

        Args:
            request_id: Unique request identifier
            client_ip: Client IP address
            query_type: DNS query type (A, AAAA, CNAME, etc.)
            domain: Domain name being queried
            response_code: DNS response code (NOERROR, NXDOMAIN, etc.)
            response_time_ms: Response time in milliseconds
            cache_hit: Whether the response came from cache
            upstream_server: Upstream server used (if any)
            response_data: List of response data (IP addresses, etc.)
            error: Error message (if any)
        """
        # Create log entry in exact format specified
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_id": request_id,
            "client_ip": client_ip,
            "query_type": query_type,
            "domain": domain,
            "response_code": response_code,
            "response_time_ms": round(response_time_ms, 2),
            "cache_hit": cache_hit,
            "upstream_server": upstream_server,
            "response_data": response_data or [],
        }

        # Add error field if present
        if error:
            log_entry["error"] = error

        # Log the entry
        self.logger.info("DNS request processed", **log_entry)

    def log_dns_error(
        self,
        request_id: str,
        client_ip: str,
        query_type: str,
        domain: str,
        error: str,
        response_time_ms: float,
    ) -> None:
        """Log DNS request that resulted in an error.

        Args:
            request_id: Unique request identifier
            client_ip: Client IP address
            query_type: DNS query type
            domain: Domain name being queried
            error: Error description
            response_time_ms: Response time in milliseconds
        """
        self.log_dns_request(
            request_id=request_id,
            client_ip=client_ip,
            query_type=query_type,
            domain=domain,
            response_code="SERVFAIL",
            response_time_ms=response_time_ms,
            cache_hit=False,
            upstream_server=None,
            response_data=None,
            error=error,
        )


class DNSRequestTracker:
    """Tracks DNS requests for performance timing and logging."""

    def __init__(self):
        """Initialize request tracker."""
        self.active_requests: Dict[str, float] = {}
        self.dns_logger = DNSRequestLogger()

    def start_request(self, request_id: Optional[str] = None) -> str:
        """Start tracking a DNS request.

        Args:
            request_id: Optional request ID, will generate if not provided

        Returns:
            Request ID for tracking
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        self.active_requests[request_id] = time.time()
        return request_id

    def end_request(
        self,
        request_id: str,
        client_ip: str,
        query_type: str,
        domain: str,
        response_code: str,
        cache_hit: bool,
        upstream_server: Optional[str] = None,
        response_data: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> float:
        """End tracking a DNS request and log the result.

        Args:
            request_id: Request ID from start_request
            client_ip: Client IP address
            query_type: DNS query type
            domain: Domain name
            response_code: DNS response code
            cache_hit: Whether response came from cache
            upstream_server: Upstream server used
            response_data: Response data
            error: Error message if any

        Returns:
            Response time in milliseconds
        """
        start_time = self.active_requests.pop(request_id, time.time())
        response_time_ms = (time.time() - start_time) * 1000

        # Log the request
        if error:
            self.dns_logger.log_dns_error(
                request_id=request_id,
                client_ip=client_ip,
                query_type=query_type,
                domain=domain,
                error=error,
                response_time_ms=response_time_ms,
            )
        else:
            self.dns_logger.log_dns_request(
                request_id=request_id,
                client_ip=client_ip,
                query_type=query_type,
                domain=domain,
                response_code=response_code,
                response_time_ms=response_time_ms,
                cache_hit=cache_hit,
                upstream_server=upstream_server,
                response_data=response_data,
            )

        return response_time_ms


def extract_dns_info(dns_message: message.Message) -> Dict[str, Any]:
    """Extract information from DNS message for logging.

    Args:
        dns_message: DNS message to extract from

    Returns:
        Dictionary with extracted DNS information
    """
    info = {
        "domain": "",
        "query_type": "",
        "response_code": "NOERROR",
        "response_data": [],
    }

    try:
        # Extract query information
        if dns_message.question:
            question = dns_message.question[0]
            info["domain"] = str(question.name).rstrip(".")
            info["query_type"] = question.rdtype.name

        # Extract response code
        info["response_code"] = rcode.to_text(dns_message.rcode())

        # Extract response data
        if dns_message.answer:
            response_data = []
            for rrset in dns_message.answer:
                for rr in rrset:
                    response_data.append(str(rr))
            info["response_data"] = response_data

    except Exception as e:
        # Log parsing error but don't fail
        logger = get_logger("dns_parser")
        logger.warning("Failed to parse DNS message", error=str(e))

    return info


def format_response_data(answer_section: Any, query_type: str) -> List[str]:
    """Format DNS response data based on query type.

    Args:
        answer_section: DNS answer section
        query_type: Type of DNS query

    Returns:
        Formatted response data list
    """
    response_data = []

    try:
        if not answer_section:
            return response_data

        for rrset in answer_section:
            for rr in rrset:
                if query_type == "A":
                    response_data.append(str(rr))
                elif query_type == "AAAA":
                    response_data.append(str(rr))
                elif query_type == "CNAME":
                    response_data.append(str(rr.target).rstrip("."))
                elif query_type == "MX":
                    response_data.append(
                        f"{rr.preference} {str(rr.exchange).rstrip('.')}"
                    )
                elif query_type == "TXT":
                    response_data.append(
                        " ".join(b.decode("utf-8") for b in rr.strings)
                    )
                elif query_type == "NS":
                    response_data.append(str(rr.target).rstrip("."))
                elif query_type == "PTR":
                    response_data.append(str(rr.target).rstrip("."))
                elif query_type == "SOA":
                    response_data.append(
                        f"{str(rr.mname).rstrip('.')} {str(rr.rname).rstrip('.')} "
                        f"{rr.serial} {rr.refresh} {rr.retry} {rr.expire} {rr.minimum}"
                    )
                else:
                    response_data.append(str(rr))

    except Exception as e:
        # Log formatting error but don't fail
        logger = get_logger("dns_formatter")
        logger.warning(
            "Failed to format response data", error=str(e), query_type=query_type
        )

    return response_data


# Global request tracker instance
_request_tracker: Optional[DNSRequestTracker] = None


def get_request_tracker() -> DNSRequestTracker:
    """Get the global DNS request tracker.

    Returns:
        DNS request tracker instance
    """
    global _request_tracker
    if _request_tracker is None:
        _request_tracker = DNSRequestTracker()
    return _request_tracker


def log_performance_event(event_type: str, duration_ms: float, **kwargs) -> None:
    """Log a performance event.

    Args:
        event_type: Type of performance event
        duration_ms: Duration in milliseconds
        **kwargs: Additional event data
    """
    logger = get_logger("dns_performance")
    logger.info(
        "Performance event",
        event_type=event_type,
        duration_ms=round(duration_ms, 2),
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **kwargs,
    )


def log_security_event(
    event_type: str, client_ip: str, domain: Optional[str] = None, **kwargs
) -> None:
    """Log a security-related event.

    Args:
        event_type: Type of security event
        client_ip: Client IP address
        domain: Domain involved (if any)
        **kwargs: Additional event data
    """
    logger = get_logger("dns_security")
    logger.warning(
        "Security event",
        event_type=event_type,
        client_ip=client_ip,
        domain=domain,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **kwargs,
    )
