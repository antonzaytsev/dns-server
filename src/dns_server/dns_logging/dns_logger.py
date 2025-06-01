"""
DNS Request/Response Logging

This module provides DNS-specific logging functionality with the exact JSON format
specified in the requirements, including request ID tracking and performance timing.
"""

import asyncio
import json
import logging
import logging.handlers
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dns import message, rcode

from .logger import get_logger


class DNSFileLogger:
    """Specialized logger that writes DNS queries to logs/dns-server.log in JSON format."""

    def __init__(self, log_file_path: str = "logs/dns-server.log"):
        """Initialize DNS file logger.

        Args:
            log_file_path: Path to the DNS log file
        """
        self.log_file_path = log_file_path
        self._setup_file_logger()

    def _setup_file_logger(self) -> None:
        """Setup dedicated file logger for DNS queries."""
        # Ensure log directory exists
        log_path = Path(self.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create dedicated logger for DNS file output
        self.file_logger = logging.getLogger("dns_file_logger")
        self.file_logger.handlers.clear()
        self.file_logger.setLevel(logging.INFO)
        self.file_logger.propagate = False  # Prevent duplicate console output

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_file_path,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)

        # Custom formatter that outputs exact JSON format
        class DNSJSONFormatter(logging.Formatter):
            def format(self, record):
                return record.getMessage()

        file_handler.setFormatter(DNSJSONFormatter())
        self.file_logger.addHandler(file_handler)

    def log_dns_query(self, domain: str, ip_addresses: List[str]) -> None:
        """Log DNS query in the specified JSON format.

        Args:
            domain: Domain name that was queried
            ip_addresses: List of IP addresses returned
        """
        # Format datetime as "YYYY-MM-DD HH:MM:SS UTC"
        current_time = datetime.now(timezone.utc)
        formatted_datetime = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Create log entry in exact format specified
        log_entry = {
            "datetime": formatted_datetime,
            "domain": domain.rstrip("."),  # Remove trailing dot if present
            "ip_address": ip_addresses,
        }

        # Write as single JSON line
        json_line = json.dumps(log_entry, separators=(",", ":"))
        self.file_logger.info(json_line)


class DNSRequestLogger:
    """DNS request/response logger with structured JSON output."""

    def __init__(self):
        """Initialize DNS logger."""
        self.logger = get_logger("dns_requests")
        # Initialize specialized file logger for DNS queries
        self.file_logger = DNSFileLogger()

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

        # Log the entry to console/structured logs
        self.logger.info("DNS request processed", **log_entry)

        # Log to specialized DNS file if successful query with IP addresses
        if (
            not error
            and response_code == "NOERROR"
            and response_data
            and query_type in ["A", "AAAA"]
        ):  # Only log A and AAAA records with IPs
            # Extract IP addresses from response data
            ip_addresses = []
            for data in response_data:
                # For A/AAAA records, the response data should be IP addresses
                # Handle both "domain IP" and just "IP" formats
                parts = data.split()
                if len(parts) >= 2:
                    # Format: "example.com. 1.2.3.4"
                    ip_addresses.append(parts[-1])
                elif len(parts) == 1:
                    # Format: "1.2.3.4"
                    ip_addresses.append(parts[0])

            if ip_addresses:
                self.file_logger.log_dns_query(domain, ip_addresses)

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

    def __init__(self, max_recent_requests: int = 1000):
        """Initialize request tracker.

        Args:
            max_recent_requests: Maximum number of recent requests to store in memory
        """
        self.active_requests: Dict[str, float] = {}
        self.dns_logger = DNSRequestLogger()

        # Store recent requests for real-time display
        self.recent_requests = deque(maxlen=max_recent_requests)
        self.max_recent_requests = max_recent_requests

        # Real-time notification callbacks
        self._query_callbacks: List[Callable[[Dict[str, Any]], None]] = []

    def add_query_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Add a callback to be called when a new DNS query is completed.

        Args:
            callback: Function to call with query data
        """
        self._query_callbacks.append(callback)

    def remove_query_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Remove a query callback.

        Args:
            callback: Function to remove
        """
        if callback in self._query_callbacks:
            self._query_callbacks.remove(callback)

    def _notify_query_callbacks(self, query_data: Dict[str, Any]) -> None:
        """Notify all registered callbacks about a new query.

        Args:
            query_data: The DNS query data
        """
        for callback in self._query_callbacks:
            try:
                # Handle both sync and async callbacks
                result = callback(query_data)
                if asyncio.iscoroutine(result):
                    # Schedule async callback
                    try:
                        loop = asyncio.get_event_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        # No event loop running, skip async callback
                        pass
            except Exception as ex:
                # Log callback errors but don't fail the main process
                logger = get_logger("dns_request_tracker")
                logger.warning(f"Error in query callback: {ex}")

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

        # Create request record for storage
        request_record = {
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
            request_record["error"] = error

        # Store in recent requests for real-time access
        self.recent_requests.appendleft(request_record)

        # Notify real-time callbacks IMMEDIATELY
        self._notify_query_callbacks(request_record)

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

    async def get_recent_requests(
        self, limit: int = 50, offset: int = 0, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Get recent DNS requests.

        Args:
            limit: Maximum number of requests to return
            offset: Number of requests to skip
            filters: Optional filters to apply

        Returns:
            List of recent DNS request records
        """
        # Convert deque to list for slicing
        requests_list = list(self.recent_requests)

        # Apply filters if provided
        if filters:
            filtered_requests = []
            for request in requests_list:
                if self._matches_filters(request, filters):
                    filtered_requests.append(request)
            requests_list = filtered_requests

        # Apply offset and limit
        start_idx = offset
        end_idx = start_idx + limit

        return requests_list[start_idx:end_idx]

    def _matches_filters(
        self, request: Dict[str, Any], filters: Dict[str, Any]
    ) -> bool:
        """Check if a request matches the given filters.

        Args:
            request: Request record to check
            filters: Filters to apply

        Returns:
            True if request matches all filters
        """
        for key, value in filters.items():
            if (
                key == "domain"
                and value.lower() not in request.get("domain", "").lower()
            ):
                return False
            elif key == "query_type" and request.get("query_type") != value:
                return False
            elif key == "client_ip" and request.get("client_ip") != value:
                return False
            elif key == "cache_hit" and request.get("cache_hit") != value:
                return False
            elif key == "since":
                # Filter by timestamp
                try:
                    since_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    request_time = datetime.fromisoformat(
                        request.get("timestamp", "").replace("Z", "+00:00")
                    )
                    if request_time < since_time:
                        return False
                except (ValueError, AttributeError):
                    # If timestamp parsing fails, skip this filter
                    continue

        return True

    def get_request_count(self) -> int:
        """Get the number of recent requests stored.

        Returns:
            Number of recent requests
        """
        return len(self.recent_requests)

    def clear_recent_requests(self) -> None:
        """Clear all stored recent requests."""
        self.recent_requests.clear()


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

        # Handle different types of answer_section structures
        for rrset in answer_section:
            # Check if rrset is iterable (list/tuple) or a single record
            if hasattr(rrset, "__iter__") and not isinstance(rrset, str):
                records = rrset
            else:
                records = [rrset]

            for rr in records:
                try:
                    if query_type == "A":
                        # For A records, convert 4-byte binary to IPv4 address
                        if hasattr(rr, "rdata") and len(rr.rdata) == 4:
                            # Convert 4 bytes to IP address
                            ip_bytes = rr.rdata
                            ip_address = f"{ip_bytes[0]}.{ip_bytes[1]}.{ip_bytes[2]}.{ip_bytes[3]}"
                            response_data.append(ip_address)
                        elif hasattr(rr, "address"):
                            response_data.append(str(rr.address))
                        else:
                            # Try to parse the string representation
                            rr_str = str(rr).strip()
                            # Look for IP pattern in the string
                            import re

                            ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
                            ip_match = re.search(ip_pattern, rr_str)
                            if ip_match:
                                response_data.append(ip_match.group())
                            else:
                                response_data.append(rr_str)
                    elif query_type == "AAAA":
                        # For AAAA records, convert 16-byte binary to IPv6 address
                        if hasattr(rr, "rdata") and len(rr.rdata) == 16:
                            # Convert 16 bytes to IPv6 address
                            import socket

                            ip_address = socket.inet_ntop(socket.AF_INET6, rr.rdata)
                            response_data.append(ip_address)
                        elif hasattr(rr, "address"):
                            response_data.append(str(rr.address))
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "CNAME":
                        if hasattr(rr, "target"):
                            response_data.append(str(rr.target).rstrip("."))
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "MX":
                        if hasattr(rr, "preference") and hasattr(rr, "exchange"):
                            response_data.append(
                                f"{rr.preference} {str(rr.exchange).rstrip('.')}"
                            )
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "TXT":
                        if hasattr(rr, "strings"):
                            response_data.append(
                                " ".join(b.decode("utf-8") for b in rr.strings)
                            )
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "NS":
                        if hasattr(rr, "target"):
                            response_data.append(str(rr.target).rstrip("."))
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "PTR":
                        if hasattr(rr, "target"):
                            response_data.append(str(rr.target).rstrip("."))
                        else:
                            response_data.append(str(rr).strip())
                    elif query_type == "SOA":
                        if hasattr(rr, "mname") and hasattr(rr, "rname"):
                            response_data.append(
                                f"{str(rr.mname).rstrip('.')} {str(rr.rname).rstrip('.')} "
                                f"{rr.serial} {rr.refresh} {rr.retry} {rr.expire} {rr.minimum}"
                            )
                        else:
                            response_data.append(str(rr).strip())
                    else:
                        response_data.append(str(rr).strip())
                except Exception as record_error:
                    # Log individual record error but continue processing
                    logger = get_logger("dns_formatter")
                    logger.debug(
                        f"Failed to format individual record: {record_error}, "
                        f"record: {rr}, query_type: {query_type}"
                    )
                    # Fallback to string conversion
                    try:
                        response_data.append(str(rr).strip())
                    except:
                        pass  # Skip this record entirely if it can't be converted

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
